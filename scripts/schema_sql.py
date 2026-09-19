#!/usr/bin/env python3
"""Generate PostgreSQL DDL for review. Run from the project root.
This does NOT apply schema changes; Django migrations are authoritative.
"""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.db import connections
from atlas import models
from atlas.dataset import TABLES,ORDER
# Build the SQL with the actual PostgreSQL backend, without opening a connection.
from django.db.backends.postgresql.base import DatabaseWrapper
connection=DatabaseWrapper({'ENGINE':'django.db.backends.postgresql','NAME':'derry','USER':'derry','PASSWORD':'','HOST':'','PORT':'','OPTIONS':{},'TIME_ZONE':None,'AUTOCOMMIT':True,'CONN_MAX_AGE':0,'CONN_HEALTH_CHECKS':False},alias='ddl')
connection.__dict__['pg_version']=170011
with connection.schema_editor(collect_sql=True,atomic=False) as editor:
 for name in ORDER:editor.create_model(TABLES[name])
 editor.create_model(models.Revision)
 editor.create_model(models.MapState)
 for extra in (models.Character,models.Tag,models.Photo,models.Photo.characters.through,models.Photo.tags.through):
  editor.create_model(extra)
 sql=editor.collected_sql
print('-- PostgreSQL 17 application schema; REVIEW ONLY, NOT an installation script.')
print('-- Apply migrations with: python manage.py migrate --noinput')
print('-- Run atlas seed separately after migrations. No novel text is required.')
print('\n'.join(sql))
print('-- Migration 0002 also inserts the singleton atlas_mapstate row (id=1).')
