"""Preserved A2 layout. Invoked by the export command in its own process."""
import math,base64,html,json
from pathlib import Path
import numpy as np
import matplotlib
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

LANGUAGES = ('en', 'ru')
STRINGS = {
    'en': {
        'book': 'S T E P H E N  K I N G  /  I T',
        'plate': 'PLATE {number:02d} / 04',
        'periods': '1957-58 / 1984-85 / HISTORICAL SITES',
        'reading': 'READING THIS SHEET',
        'confidence': (
            ('A', 'Text-anchored relationship'),
            ('B', 'Inferred position'),
            ('C', 'Proposed location'),
        ),
        'confidence_note': ('All coordinates are reconstructed. A names a relationship stated '
                            'in the text; it does not certify an exact position.'),
        'map_key': 'MAP KEY',
        'key_items': (
            ('forest', 'Woodland and scrub'),
            ('park', 'Park / open ground'),
            ('water', 'Surface water'),
        ),
        'covered': 'Covered watercourse',
        'footpath': 'Approximate footpath',
        'contours': ('Contour strokes show conceptual relief only. Unlabelled buildings, minor '
                     'streets and parcel shapes are illustrative. No numerical elevations are implied.'),
        'places': 'PLACES ON THIS SHEET',
        'relationships': 'LOCAL RELATIONSHIPS',
        'source_note': ('Source of inspiration: Stephen King, IT (1986). Chapter references and '
                        'reconstruction decisions are in the map database. The original research '
                        'notes are retained as a baseline reference.'),
        'intro': {
            'city': ('Four sheets form one map. Sheet 2 expands the town centre; sheets 3 and 4 '
                     "reveal the Barrens and the Losers' ground. Smaller downtown sites are indexed on sheet 2."),
            'central': ('Both periods and the historical interludes share one plan. Old businesses '
                        'and destroyed places retain their locations; dates and qualifications are '
                        'in the companion notes.'),
            'barrens': ('A tapered river valley, approximately 4.8 km long and 2.4 km wide in the '
                        'novel. The border, contours, vegetation and footpaths are reconstructed.'),
            'camp': ('The precise shape of this small area is inferred. The western branch, the path '
                     'from the Kansas bridge and the separate entry cylinder preserve the book\'s '
                     'local relationships.'),
        },
        'local_relationships': (
            '44  The small western arm is dammed. The broader eastern arm remains a distinct channel.',
            '43  The clubhouse and smoke-hole are one place. Its stated width is about 1.5 m; the numbered symbol is enlarged for reading.',
            '45  Silver is hidden under the bridge over the tributary. The route to the clearing follows the slope down to the river.',
            "47  The entry cylinder is drawn separately from Pumphouse #3 and from Patrick's trail-end cylinder.",
            'Paths and vegetation describe a plausible landscape. Their individual bends and boundaries are not supplied by King.',
        ),
        'scale': '1:{scale:,} at A2 - reconstructed distances',
        'kilometres': '{value:g} km',
        'metres': '{value:g} m',
        'reconstruction': 'A NOVEL-BASED RECONSTRUCTION',
        'print': 'A2 / 594 x 420 mm / Print at 100% for stated scale',
        'footer': ('Composite map: former sites retained. Surface geography only. Map geometry and '
                   'relief are inferred; no screen adaptation geography used.'),
        'pdf_title': "Derry - A literary atlas of Stephen King's IT",
        'pdf_author': 'Novel-based reconstruction prepared for the reader',
        'svg_description': ('A printable literary map reconstructed from Stephen King\'s IT. '
                            'Place and street names are in English.'),
    },
    'ru': {
        'book': 'С Т И В Е Н  К И Н Г  /  « О Н О »',
        'plate': 'ЛИСТ {number:02d} / 04',
        'periods': '1957–58 / 1984–85 / ИСТОРИЧЕСКИЕ МЕСТА',
        'reading': 'КАК ЧИТАТЬ ЭТОТ ЛИСТ',
        'confidence': (
            ('A', 'Связь закреплена текстом'),
            ('B', 'Положение выведено'),
            ('C', 'Место предполагается'),
        ),
        'confidence_note': ('Все координаты реконструированы. Уровень A означает, что взаимное '
                            'положение закреплено текстом, но не подтверждает точную координату.'),
        'map_key': 'УСЛОВНЫЕ ОБОЗНАЧЕНИЯ',
        'key_items': (
            ('forest', 'Лес и кустарник'),
            ('park', 'Парк / открытая местность'),
            ('water', 'Открытая вода'),
        ),
        'covered': 'Закрытый водоток',
        'footpath': 'Приблизительная тропа',
        'contours': ('Контуры передают только условный рельеф. Неподписанные здания, мелкие улицы '
                     'и границы участков иллюстративны. Численные высоты не подразумеваются.'),
        'places': 'МЕСТА НА ЭТОМ ЛИСТЕ',
        'relationships': 'ЛОКАЛЬНЫЕ СВЯЗИ',
        'source_note': ('Источник: роман Стивена Кинга «Оно» (1986). Ссылки на главы и решения по '
                        'реконструкции хранятся в базе карты. Исходные исследовательские заметки '
                        'сохранены как отправная точка.'),
        'intro': {
            'city': ('Четыре листа образуют одну карту. Лист 2 подробно показывает центр города, '
                     'листы 3 и 4 — Пустоши и поляну Неудачников. Небольшие места в центре '
                     'перечислены на листе 2.'),
            'central': ('Оба периода и интерлюдии объединены на одном плане. Прежние места '
                        'сохранены; даты и оговорки — на сайте.'),
            'barrens': ('Сужающаяся речная долина: в романе её длина около 4,8 км, ширина — около '
                        '2,4 км. Границы, рельеф, растительность и тропы реконструированы.'),
            'camp': ('Точная форма этого небольшого участка выведена косвенно. Западный рукав, '
                     'тропа от моста на Канзас-стрит и отдельный входной цилиндр сохраняют локальные '
                     'связи, описанные в книге.'),
        },
        'local_relationships': (
            '44  Небольшой западный рукав перегорожен. Более широкий восточный рукав остаётся отдельным руслом.',
            '43  Клуб и дымовое отверстие — одно место. Указанная ширина — около 1,5 м; номерной знак увеличен для читаемости.',
            '45  Сильвер спрятан под мостом через приток. Путь к поляне спускается по склону к реке.',
            '47  Входной цилиндр показан отдельно от насосной станции № 3 и цилиндра в конце тропы Патрика.',
            'Тропы и растительность показывают правдоподобный ландшафт. Их точные изгибы и границы в книге не заданы.',
        ),
        'scale': '1:{scale:,}, формат A2 · реконструированные расстояния',
        'kilometres': '{value:g} км',
        'metres': '{value:g} м',
        'reconstruction': 'РЕКОНСТРУКЦИЯ ПО РОМАНУ',
        'print': 'A2 / 594 × 420 мм / Печатать в масштабе 100%',
        'footer': ('Сводная карта: прежние места сохранены. Показана только наземная география. '
                   'Геометрия и рельеф выведены косвенно; география экранизаций не использована.'),
        'pdf_title': 'Дерри — литературный атлас романа Стивена Кинга «Оно»',
        'pdf_author': 'Реконструкция по роману, подготовленная для читателя',
        'svg_description': ('Печатная литературная карта, реконструированная по роману Стивена '
                            'Кинга «Оно». Названия мест, улиц и природных объектов даны на русском.'),
        'views': {
            'city': ('ДЕРРИ', 'Город, Пустоши и загородные дороги'),
            'central': ('ЦЕНТР ДЕРРИ', 'Улицы, мосты и памятные места'),
            'barrens': ('ПУСТОШИ', 'Речная долина, старая железная дорога и Канзас-стрит'),
            'camp': ('ПОЛЯНА НЕУДАЧНИКОВ', 'Подробная реконструкция поляны и речных берегов'),
        },
    },
}

def hexrgb(s):return tuple(int(s[i:i+2],16)/255 for i in (1,3,5))
class Surface:
    def __init__(self,c=None,width=1683.78,height=1190.55):self.c=c;self.w=width;self.h=height;self.svg=[]
    def color(self,col,stroke=False):
        if self.c and col:(self.c.setStrokeColorRGB if stroke else self.c.setFillColorRGB)(*hexrgb(col))
    def path(self,pts,fill=None,stroke=None,width=1,close=False,dash=None):
        if len(pts)<2:return
        if self.c:
            p=self.c.beginPath();p.moveTo(pts[0][0],self.h-pts[0][1])
            for x,y in pts[1:]:p.lineTo(x,self.h-y)
            if close:p.close()
            self.color(fill);self.color(stroke,True);self.c.setLineWidth(width);self.c.setLineJoin(1);self.c.setLineCap(1)
            self.c.setDash(dash or [])
            self.c.drawPath(p,fill=bool(fill),stroke=bool(stroke))
        st=f' fill="{fill or "none"}" stroke="{stroke or "none"}" stroke-width="{width:.3f}" stroke-linejoin="round" stroke-linecap="round"'
        if dash:st+=' stroke-dasharray="'+' '.join(f'{v:.2f}' for v in dash)+'"'
        d='M'+' L'.join(f'{x:.2f},{y:.2f}' for x,y in pts)+(' Z' if close else '')
        self.svg.append(f'<path d="{d}"{st}/>')
    def box(self,x,y,w,h,fill=None,stroke=None,lw=1):self.path([[x,y],[x+w,y],[x+w,y+h],[x,y+h]],fill,stroke,lw,True)
    def circle(self,x,y,r,fill=None,stroke=None,lw=1):
        if self.c:
            self.color(fill);self.color(stroke,True);self.c.setLineWidth(lw);self.c.setDash([]);self.c.circle(x,self.h-y,r,stroke=bool(stroke),fill=bool(fill))
        self.svg.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" fill="{fill or "none"}" stroke="{stroke or "none"}" stroke-width="{lw:.3f}"/>')
    def text(self,x,y,t,size=10,font='Sans',col=None,anchor='start',angle=0,halo=False):
        col=col or C['ink']
        family='DejaVu Serif' if 'Serif' in font else 'DejaVu Sans'
        weight='bold' if 'Bold' in font else 'normal';italic='italic' if font=='Italic' else 'normal'
        if self.c:
            self.c.saveState();self.c.translate(x,self.h-y);self.c.rotate(angle);self.c.setFont(font,size);self.color(col)
            tw=pdfmetrics.stringWidth(t,font,size);offset=0 if anchor=='start' else (-tw/2 if anchor=='middle' else -tw)
            if halo:
                ob=self.c.beginText();ob.setTextOrigin(offset,0);ob.setFont(font,size);ob.setTextRenderMode(1);self.color(C['paper'],True);self.c.setLineWidth(2.5);ob.textOut(t);ob.setTextRenderMode(0);self.c.drawText(ob)
            self.color(col)
            ob=self.c.beginText();ob.setTextOrigin(offset,0);ob.setFont(font,size);ob.setTextRenderMode(0);ob.textOut(t);self.c.drawText(ob);self.c.restoreState()
        h=f' paint-order="stroke" stroke="{C["paper"]}" stroke-width="2.6" stroke-linejoin="round"' if halo else ''
        self.svg.append(f'<text x="{x:.2f}" y="{y:.2f}" font-family="{family}" font-size="{size}" font-weight="{weight}" font-style="{italic}" text-anchor="{anchor}" fill="{col}" transform="rotate({-angle} {x:.2f} {y:.2f})"{h}>{html.escape(t)}</text>')
    def image(self,x,y,w,h,path):
        if self.c:self.c.drawImage(str(path),x,self.h-y-h,w,h,mask='auto')
        b=base64.b64encode(Path(path).read_bytes()).decode()
        self.svg.append(f'<image x="{x}" y="{y}" width="{w}" height="{h}" href="data:image/png;base64,{b}"/>')
    def wrap(self,x,y,t,width,size=10,leading=15,font='Sans',col=None):
        words=t.split();line='';lines=[]
        for w in words:
            new=(line+' '+w).strip()
            if pdfmetrics.stringWidth(new,font,size)>width and line:lines.append(line);line=w
            else:line=new
        if line:lines.append(line)
        for l in lines:self.text(x,y,l,size,font,col);y+=leading
        return y

FRAME=(12*mm,40*mm,440*mm,350*mm)
def projector(view):
    a,b,c,d=view['bounds'];fx,fy,fw,fh=FRAME
    sc=fw/(c-a)
    return lambda x,y:(fx+(x-a)*sc,fy+(d-y)*sc),sc
def draw_base(surf,view):
    tr,k=projector(view);x0,y0,w,h=FRAME
    surf.box(x0,y0,w,h,C['paper'])
    if surf.c:
        surf.c.saveState();p=surf.c.beginPath();p.rect(x0,surf.h-y0-h,w,h);surf.c.clipPath(p,stroke=0,fill=0)
    surf.svg.append(f'<defs><clipPath id="mapclip"><rect x="{x0}" y="{y0}" width="{w}" height="{h}"/></clipPath></defs><g clip-path="url(#mapclip)">')
    for o in BASE:
        typ=o['type']
        if typ in ['line','poly']:
            surf.path([tr(*p) for p in o['points']],o.get('fill'),o.get('stroke'),max(.20,o.get('width',1)*k),typ=='poly',[z*k for z in o['dash']] if o.get('dash') else None)
        elif typ=='circle':surf.circle(*tr(o['x'],o['y']),o['r']*k,o['fill'],o.get('stroke'),max(.12,o['width']*k))
        elif typ=='rect':
            cx,cy=o['x'],o['y'];ang=math.radians(o['angle']);cs,sn=math.cos(ang),math.sin(ang)
            pts=[]
            for xx0,yy0 in [(-.5,-.5),(.5,-.5),(.5,.5),(-.5,.5)]:
                xx0*=o['w'];yy0*=o['h'];pts.append(tr(cx+xx0*cs-yy0*sn,cy+xx0*sn+yy0*cs))
            surf.path(pts,o['fill'],o.get('stroke'),max(.1,o['width']*k),True)
        elif typ=='image':
            xx0,yy0=tr(o['x'],o['y']+o['h']);surf.image(xx0,yy0,o['w']*k,o['h']*k,o['path'])
    # A geographic grid indexes the atlas without suggesting Earth coordinates.
    grid=1000 if view['id']=='city' else (500 if view['id']!='camp' else 100)
    a,b,c,d=view['bounds']
    for x in range(math.ceil(a/grid)*grid,int(c),grid):
        surf.path([tr(x,b),tr(x,d)],None,'#d6d5c6',.35)
    for y in range(math.ceil(b/grid)*grid,int(d),grid):
        surf.path([tr(a,y),tr(c,y)],None,'#d6d5c6',.35)
    # Flow-direction arrows are geometric, not screenshots or symbolic river reversals.
    for x,y,angle in PRINT['flow_arrows']:
        if a<x<c and b<y<d:
            xx0,yy0=tr(x,y);ang=math.radians(angle);u=np.array([math.cos(ang),-math.sin(ang)]);v=np.array([-u[1],u[0]])
            tip=np.array([xx0,yy0])+u*10
            surf.path([(np.array([xx0,yy0])-u*10).tolist(),tip.tolist()],None,'#3d7380',.9)
            surf.path([(tip-u*4+v*2.5).tolist(),tip.tolist(),(tip-u*4-v*2.5).tolist()],None,'#3d7380',.9)
    surf.svg.append('</g>')
    if surf.c:surf.c.restoreState()
    surf.box(x0,y0,w,h,None,'#829080',.7)

def intersects(a,b,pad=0):return not(a[2]+pad<b[0] or a[0]-pad>b[2] or a[3]+pad<b[1] or a[1]-pad>b[3])
def fitbox(b):
    x,y,w,h=FRAME
    return b[0]>x+4 and b[1]>y+4 and b[2]<x+w-4 and b[3]<y+h-4
LABEL_LOG=[]
def draw_labels(surf,view):
    tr,k=projector(view);bounds=view['bounds'];occupied=[(442*mm-15,54*mm-22,442*mm+15,54*mm+29)]
    # Map place labels have higher precedence than road/landscape names.
    sites=[p for p in D['sites'] if bounds[0]<p['x']<bounds[2] and bounds[1]<p['y']<bounds[3]]
    for p in sorted(sites,key=lambda p:(p['rank'],p['id'])):
        x,y=tr(p['x'],p['y']);color=KIND[p['kind']]
        # In the city-wide sheet, smaller downtown sites are indexed on sheet 2.
        if view['id']=='city' and p['rank']>1 and PRINT['downtown_bounds'][0]<p['x']<PRINT['downtown_bounds'][2] and PRINT['downtown_bounds'][1]<p['y']<PRINT['downtown_bounds'][3]:continue
        num=str(p['id']).zfill(2);r=6.0
        choices=[(0,0)]+[(math.cos(a)*rr,math.sin(a)*rr) for rr in [14,24,38] for a in np.linspace(0,2*math.pi,10,endpoint=False)]
        chosen=None
        for dx,dy in choices:
            bb=(x+dx-r-1,y+dy-r-1,x+dx+r+1,y+dy+r+1)
            if fitbox(bb) and not any(intersects(bb,ob,1) for ob in occupied):chosen=(x+dx,y+dy,bb);break
        if chosen is None:chosen=(x,y,(x-r,y-r,x+r,y+r))
        mx,my,bb=chosen;occupied.append(bb)
        if abs(mx-x)+abs(my-y)>2:
            surf.path([[x,y],[mx,my]],None,color,.5);surf.circle(x,y,1.6,color)
        if p['confidence']=='C':
            surf.path([[mx,my-r-1],[mx+r+1,my],[mx,my+r+1],[mx-r-1,my]],C['paper'],color,1.1,True)
        else:surf.circle(mx,my,r,color if p['confidence']=='A' else C['paper'],color,.9)
        surf.text(mx,my+2.25,num,6.4,'SansBold',C['paper'] if p['confidence']=='A' else color,'middle')
        # All points are numbered. Dense names move to the facing index.
        show=(view['id'] in ['camp','barrens'] or p['rank']==1 or (view['id']=='central' and p['rank']<=2))
        if not show:continue
        txt=p['short'];size=9 if view['id']=='camp' else 8.5
        tw=pdfmetrics.stringWidth(txt,'SansBold',size)
        candidates=[]
        for dy in [3,-9,15,-20,28,-32]:
            candidates.extend([(mx+10,my+dy,'start'),(mx-10,my+dy,'end')])
        placed=False
        for xx0,yy0,anc in candidates:
            bb2=(xx0 if anc=='start' else xx0-tw,yy0-size-1,xx0+tw if anc=='start' else xx0,yy0+2)
            if fitbox(bb2) and not any(intersects(bb2,ob,1.8) for ob in occupied):
                occupied.append(bb2);surf.text(xx0,yy0,txt,size,'SansBold',C['ink'],anc,halo=True);placed=True;break
        LABEL_LOG.append(dict(view=view['id'],id=p['id'],label=placed))
    for l in sorted(LABELS,key=lambda l:{'region':0,'road':1,'water':2,'land':3}[l['kind']]):
        if view['id'] not in l['views']:continue
        if not(bounds[0]<l['x']<bounds[2] and bounds[1]<l['y']<bounds[3]):continue
        x,y=tr(l['x'],l['y']);t=l['text'];sz=l['size'];tw=pdfmetrics.stringWidth(t,l['font'],sz);ang=math.radians(l['angle'])
        ww=abs(tw*math.cos(ang))+abs(sz*math.sin(ang));hh=abs(tw*math.sin(ang))+abs(sz*math.cos(ang))
        bb=(x-ww/2-2,y-hh/2-3,x+ww/2+2,y+hh/2+3)
        if fitbox(bb) and not any(intersects(bb,b,2) for b in occupied):
            surf.text(x,y,t,sz,l['font'],C['waterline'] if l['kind']=='water' else '#65725d','middle',l['angle'],True);occupied.append(bb)
    return sites

def scale_bar(s,x,y,view):
    val=PRINT['scale_bars'][view['id']]
    lengthpt=val/view['scale']*1000*mm
    for i in range(4):s.box(x+i*lengthpt/4,y,lengthpt/4,5,C['ink'] if i%2==0 else C['paper'],C['ink'],.5)
    s.text(x,y+17,'0',8)
    unit='kilometres' if val>=1000 else 'metres'
    s.text(x+lengthpt/2,y+17,T[unit].format(value=val/2000 if val>=1000 else val/2),8,anchor='middle')
    s.text(x+lengthpt,y+17,T[unit].format(value=val/1000 if val>=1000 else val),8,anchor='end')
    s.text(x,y-9,T['scale'].format(scale=view['scale']),8,'Sans',C['muted'])

def sidebar(s,view,sites):
    x=465*mm;y=43*mm;w=115*mm
    s.text(x,y,T['reading'],11,'SansBold');y+=19
    intro=T['intro'][view['id']]
    y=s.wrap(x,y,intro,w,9.2,13);y+=15
    for conf,label in T['confidence']:
        col=C['ink'];mx=x+5
        if conf=='C':s.path([[mx,y-7],[mx+6,y-1],[mx,y+5],[mx-6,y-1]],C['paper'],col,.9,True)
        else:s.circle(mx,y-1,5,col if conf=='A' else C['paper'],col,.9)
        s.text(x+19,y+2,f'{conf}  {label}',8.7);y+=18
    y=s.wrap(x,y+4,T['confidence_note'],w,8.4,11.8,'Italic',C['muted'])
    y+=18;s.text(x,y,T['map_key'],10,'SansBold');y+=18
    for color_key,lab in T['key_items']:
        color=C[color_key]
        s.box(x,y-8,14,8,color,'#aab39d',.4);s.text(x+21,y,lab,8.6);y+=16
    s.path([[x,y-3],[x+16,y-3]],None,C['waterline'],1.8,False,[4,3]);s.text(x+21,y,T['covered'],8.6);y+=16
    s.path([[x,y-3],[x+16,y-3]],None,'#9d8257',1,False,[3,2]);s.text(x+21,y,T['footpath'],8.6);y+=18
    y=s.wrap(x,y,T['contours'],w,8.2,11.6,'Italic',C['muted']);y+=20
    s.text(x,y,T['places'],10,'SansBold');y+=18
    if view['id']=='city':entries=[p for p in sites if not(p['rank']>1 and PRINT['downtown_bounds'][0]<p['x']<PRINT['downtown_bounds'][2] and PRINT['downtown_bounds'][1]<p['y']<PRINT['downtown_bounds'][3])]
    else:entries=sites
    # A2 side index is deliberately kept at a readable 8.4 pt.
    for p in sorted(entries,key=lambda z:z['id']):
        label=p['short'];size=8.3
        s.text(x,y,str(p['id']).zfill(2),size,'SansBold',KIND[p['kind']]);
        remaining=w-27
        if pdfmetrics.stringWidth(label,'Sans',size)>remaining:
            words=label.split();line=''
            for word in words:
                if pdfmetrics.stringWidth((line+' '+word).strip(),'Sans',size)>remaining:break
                line=(line+' '+word).strip()
            tail=label[len(line):].strip();s.text(x+25,y,line,size);y+=11.5;s.text(x+25,y,tail,size)
        else:s.text(x+25,y,label,size)
        y+=11 if view['id']=='city' else 12
    if view['id']=='camp':
        y+=22;s.text(x,y,T['relationships'],10,'SansBold');y+=18
        for para in T['local_relationships']:
            y=s.wrap(x,y,para,w,9,13);y+=12
    # Footer source panel is fixed; overflowing content is a build error.
    if y>373*mm:raise RuntimeError(f'Sidebar overflow on {view["id"]}: {y/mm:.1f} mm')
    s.path([[x,379*mm],[x+w,379*mm]],None,C['line'],.7)
    s.wrap(x,385*mm,T['source_note'],w,8,11,'Sans',C['muted'])

def make_pdf():
    dest=OUT/'Derry_Print_Atlas.pdf';c=canvas.Canvas(str(dest),pagesize=(594*mm,420*mm),pageCompression=1)
    c.setTitle(T['pdf_title']);c.setAuthor(T['pdf_author'])
    for no,view in enumerate(VIEWS,1):
        title,subtitle=(T.get('views',{}).get(view['id']) or (view['title'],view['subtitle']))
        surf=Surface(c,594*mm,420*mm);surf.box(0,0,surf.w,surf.h,C['paper'])
        surf.text(12*mm,15*mm,T['book'],8.5,'SansBold',C['muted'])
        surf.text(12*mm,30*mm,title,29,'SerifBold')
        surf.text(195*mm,24*mm,subtitle,11,'Sans',C['muted'])
        surf.text(580*mm,15*mm,T['plate'].format(number=no),9,'SansBold',anchor='end')
        surf.text(580*mm,28*mm,T['periods'],8,'Sans',C['muted'],'end')
        draw_base(surf,view);sites=draw_labels(surf,view);sidebar(surf,view,sites)
        # North, placed consistently within a blank corner of the map.
        nx0=442*mm;ny0=54*mm
        surf.box(nx0-14,ny0-21,28,49,C['paper'])
        surf.text(nx0,ny0-6,'N',10,'SansBold',anchor='middle')
        surf.path([[nx0,ny0],[nx0-5,ny0+18],[nx0,ny0+13],[nx0+5,ny0+18]],C['ink'],None,0,True)
        scale_bar(surf,13*mm,401*mm,view)
        surf.text(450*mm,405*mm,T['reconstruction'],8,'SansBold',C['muted'],'end')
        surf.text(580*mm,405*mm,'derryfiles.space',8,'SansBold',C['ink'],'end')
        surf.text(580*mm,413*mm,T['print'],8,'Sans',C['muted'],'end')
        surf.text(13*mm,417*mm,T['footer'],7.8,'Sans',C['muted'])
        svg=('<svg xmlns="http://www.w3.org/2000/svg" lang="'+LANG+'" width="594mm" '
             'height="420mm" viewBox="0 0 '+str(594*mm)+' '+str(420*mm)+'"><title>'
             +html.escape(title)+'</title><desc>'+html.escape(T['svg_description'])+'</desc>'
             +''.join(surf.svg)+'</svg>')
        (OUT/f'derry_{view["id"]}.svg').write_text(svg)
        c.showPage()
    c.save()
    (OUT/'label_audit.json').write_text(json.dumps(LABEL_LOG,indent=2))
    print('PDF',dest,'objects',len(BASE))

def _render_language(payload, output, fmt, language):
    global C,KIND,D,BASE,LABELS,VIEWS,PRINT,OUT,LABEL_LOG,T,LANG
    if language not in LANGUAGES:raise ValueError(f'Unsupported print language: {language}')
    output.mkdir(parents=True,exist_ok=True)
    LANG=language;T=STRINGS[language]
    C=payload['palette'];KIND=payload['colors'];D=payload['data']
    LABELS=payload['labels'];VIEWS=payload['views'];PRINT=payload['print'];OUT=output;LABEL_LOG=[]
    for n,f in [('Sans','DejaVuSans.ttf'),('SansBold','DejaVuSans-Bold.ttf'),('Serif','DejaVuSerif.ttf'),('SerifBold','DejaVuSerif-Bold.ttf'),('Italic','DejaVuSans-Oblique.ttf')]:
        candidates=[Path('/usr/share/fonts/truetype/dejavu')/f,Path(matplotlib.get_data_path())/'fonts/ttf'/f]
        pdfmetrics.registerFont(TTFont(n,str(next(p for p in candidates if p.exists()))))
    relief=OUT/'derry_relief.png';relief.write_bytes(base64.b64decode(payload['relief'].split(',',1)[1]))
    a,b,c,d=payload['extent']
    BASE=[dict(type='image',x=a,y=b,w=c-a,h=d-b,path=str(relief))]+payload['base']
    make_pdf()
    import json
    (OUT/'manifest.json').write_text(json.dumps({'revision':payload['revision'],'digest':payload['digest'],'format':fmt,'language':language},indent=2))
    if fmt=='svg':(OUT/'Derry_Print_Atlas.pdf').unlink()
    if fmt=='pdf':
        for view in VIEWS:(OUT/f'derry_{view["id"]}.svg').unlink()

def render(payload, output, fmt, language='en'):
    from .localized_names import localize_map_payload
    if language=='all':
        for lang in LANGUAGES:
            rendered=localize_map_payload(payload) if lang=='ru' else payload
            _render_language(rendered,output/lang,fmt,lang)
        (output/'manifest.json').write_text(json.dumps({
            'revision':payload['revision'],'digest':payload['digest'],'format':fmt,
            'languages':list(LANGUAGES)},indent=2))
    else:
        rendered=localize_map_payload(payload) if language=='ru' else payload
        _render_language(rendered,output,fmt,language)
