import copy
import io
import json
import tempfile
from pathlib import Path
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from atlas import dataset as ds
from atlas.models import Feature, MapState, Revision
from atlas.rendering import compile_payload, current_payload


class AtlasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        MapState.objects.get_or_create(pk=1)
        cls.seed = json.loads((settings.BASE_DIR/'data/initial.json').read_text())
        ds.commit(lambda _: cls.seed, 'test', 'seed', seed=True)

    def cmd(self, *args):
        out = io.StringIO()
        call_command('atlas', *args, stdout=out)
        return out.getvalue()

    def test_original_identifiers_and_evidence(self):
        self.assertEqual(set(Feature.objects.filter(object_type='site').values_list('key',flat=True)), {str(i) for i in range(1,84)})
        self.assertEqual(set(Feature.objects.filter(object_type='unplaced').values_list('key',flat=True)), {'U'+str(i) for i in range(1,10)})
        self.assertEqual(Feature.objects.filter(object_type='site',evidence__isnull=False).distinct().count(),83)

    def test_edit_restart_and_seed_preserve_changes(self):
        self.cmd('edit','12','--name','Library corrected','--x','-1490','--y','-505','--author','dev','--reason','test')
        rev = MapState.objects.get(pk=1).revision_id
        self.assertIn('already initialized',self.cmd('seed'))
        call_command('migrate',verbosity=0)
        self.assertEqual(MapState.objects.get(pk=1).revision_id,rev)
        self.assertEqual(Feature.objects.get(pk='12').name,'Library corrected')

    def test_linked_wings_and_markers_move_together(self):
        original,_ = ds.read_current()
        before = compile_payload(original,1)
        f = next(f for f in original['tables']['feature'] if f['key']=='12')
        g = next(g for g in original['tables']['geometry'] if g['key']==f['geometry_id'])
        x,y = g['shape']['x'],g['shape']['y']
        self.cmd('edit','12','--x',str(x+80),'--y',str(y-40),'--name','Library corrected','--author','dev','--reason','move')
        after = compile_payload(*ds.read_current())
        a = [o for o in before['base'] if o.get('feature_id')=='12']
        b = [o for o in after['base'] if o.get('feature_id')=='12']
        self.assertGreaterEqual(len(a),4)  # grounds, two wings, glass passage
        for o,n in zip(a,b):
            if 'points' in o:
                for u,v in zip(o['points'],n['points']):
                    self.assertAlmostEqual(v[0]-u[0],80,places=2);self.assertAlmostEqual(v[1]-u[1],-40,places=2)
            else:
                self.assertAlmostEqual(n['x']-o['x'],80);self.assertAlmostEqual(n['y']-o['y'],-40)
        site = next(s for s in after['data']['sites'] if s['id']==12)
        self.assertEqual((site['x'],site['y'],site['short']),(x+80,y-40,'Library corrected'))

    def test_atomic_patch_rejects_bad_second_operation(self):
        before,rev = ds.read_current()
        changes=[{'op':'update','table':'feature','key':'12','values':{'name':'Must not persist'}},
                 {'op':'update','table':'geometry','key':'g:12','values':{'shape':{'type':'point','x':float('nan'),'y':0}}}]
        with self.assertRaises(ValueError):
            ds.commit(lambda d:ds.patch(d,changes),'dev','invalid batch')
        self.assertEqual(ds.read_current(),(before,rev))

    def test_dry_run_and_stale_revision(self):
        _,rev = ds.read_current()
        self.cmd('edit','12','--name','Preview','--author','dev','--reason','preview','--dry-run')
        self.assertNotEqual(Feature.objects.get(pk='12').name,'Preview')
        with self.assertRaises(CommandError):
            self.cmd('edit','12','--name','Conflict','--author','dev','--reason','conflict','--expected-revision',str(rev+100))

    def test_export_import_history_and_rollback(self):
        before,first = ds.read_current()
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'export.json';self.cmd('export',str(path))
            self.assertEqual(ds.digest(json.loads(path.read_text())),ds.digest(before))
            self.cmd('delete','12','--author','dev','--reason','delete')
            self.assertFalse(Feature.objects.filter(pk='12').exists())
            self.cmd('import',str(path),'--author','dev','--reason','restore export')
            self.assertEqual(ds.digest(ds.read_current()[0]),ds.digest(before))
            self.cmd('edit','12','--name','Changed','--author','dev','--reason','edit')
            self.cmd('rollback',str(first),'--author','dev','--reason','undo')
            self.assertEqual(ds.digest(ds.read_current()[0]),ds.digest(before))
            self.assertGreater(Revision.objects.count(),3)

    def test_add_delete_feature_and_sources(self):
        changes=[{'op':'add','table':'geometry','key':'g:84','values':{'shape':{'type':'point','x':0,'y':0}}},
            {'op':'add','table':'feature','key':'84','values':{'object_type':'site','name':'Review example','short':'Example','kind':'Historical','confidence':'C','geometry_id':'g:84'}},
            {'op':'add','table':'evidence','key':'e:84:0','values':{'feature_id':'84','source_id':'novel','reference':'Developer review'}}]
        ds.commit(lambda d:ds.patch(d,changes),'dev','add')
        self.assertTrue(Feature.objects.filter(pk='84').exists())
        self.cmd('delete','84','--author','dev','--reason','remove')
        self.assertFalse(Feature.objects.filter(pk='84').exists())

    def test_explicit_short_label_and_exact_snapshot_restore(self):
        original_short = Feature.objects.get(pk='12').short
        self.cmd('edit','12','--name','Alternate full library title','--short',original_short,
                 '--author','dev','--reason','Keep deliberate short label')
        self.assertEqual(Feature.objects.get(pk='12').short, original_short)
        target, rev = ds.read_current()
        self.assertEqual(ds.digest(target), Revision.objects.get(pk=rev).digest)
        self.cmd('edit','12','--name','Later full title','--short',original_short,
                 '--author','dev','--reason','Second change')
        self.cmd('rollback',str(rev),'--author','dev','--reason','Exact snapshot')
        self.assertEqual(ds.digest(ds.read_current()[0]), ds.digest(target))

    @override_settings(ALLOWED_HOSTS=['testserver'], STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
    def test_read_api_cache_invalidation_and_no_public_writes(self):
        with tempfile.TemporaryDirectory() as td, override_settings(ARTIFACT_ROOT=Path(td)):
            response=self.client.get('/api/v1/map/')
            self.assertEqual(response.status_code,200)
            self.assertEqual(len(response.json()['data']['sites']),83)
            etag=response['ETag']
            self.assertEqual(self.client.get('/api/v1/map/',HTTP_IF_NONE_MATCH=etag).status_code,304)
            self.cmd('edit','12','--description','Updated evidence','--author','dev','--reason','update')
            changed=self.client.get('/api/v1/map/',HTTP_IF_NONE_MATCH=etag)
            self.assertEqual(changed.status_code,200);self.assertNotEqual(changed['ETag'],etag)
            self.assertEqual(next(s for s in changed.json()['data']['sites'] if s['id']==12)['note'],'Updated evidence')
        for verb in ['post','put','patch','delete']:
            self.assertEqual(getattr(self.client,verb)('/api/v1/map/').status_code,405)
        self.assertEqual(self.client.get('/admin/').status_code,404)

    def test_terrain_is_derived_from_current_parameters(self):
        before,rev=ds.read_current()
        a=compile_payload(before,rev)
        config=next(x['value'] for x in before['tables']['settings'] if x['key']=='terrain')
        config['hills'][0][2] += 20
        ds.validate(before)
        b=compile_payload(before,rev)
        self.assertNotEqual(a['relief'],b['relief'])

    def test_fk_and_invalid_geometry_validation(self):
        doc,_=ds.read_current()
        doc['tables']['component'][0]['style_id']='missing'
        with self.assertRaises(ValueError):ds.validate(doc)
        doc,_=ds.read_current()
        doc['tables']['geometry'][0]['shape']={'type':'line','points':[[0,0]]}
        with self.assertRaises(ValueError):ds.validate(doc)
