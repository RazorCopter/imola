"""Build a browseable catalog and contact sheets from actual Chromium PNGs.
Run from frontend/: python e2e/sol/catalog.py (requires Pillow for sheets).
"""
from pathlib import Path
import hashlib, json, html
from PIL import Image, ImageDraw
root=Path(__file__).resolve().parents[3]/'outputs'/'visual-review'/'sol-final'
sheets=root/'review-sheets';sheets.mkdir(exist_ok=True)
routes=['dashboard','progetti','wallet','organico','costi','riconciliazione','anomalie','revisione','amministrazione']
main_names=set()
groups={}
for route in routes:
 names=[f'{route}-{suffix}.png' for suffix in ['dark-1920x1080','dark-1600x900','dark-1440x900','dark-1366x768','dark-1024x768','light-1440x900']]
 groups[route]=names;main_names.update(names)
others=sorted(p.name for p in root.glob('*.png') if p.name not in main_names)
for offset in range(0,len(others),4):groups[f'details-{offset//4+1:02}']=others[offset:offset+4]
for group,names in groups.items():
 cols=2;cell_width=800;cell_height=536;rows=(len(names)+cols-1)//cols
 sheet=Image.new('RGB',(cols*cell_width,rows*cell_height),'#e2e8f0');draw=ImageDraw.Draw(sheet)
 for index,name in enumerate(names):
  path=root/name
  if not path.exists():continue
  image=Image.open(path).convert('RGB');image.thumbnail((cell_width,500))
  x=index%cols*cell_width;y=index//cols*cell_height
  sheet.paste(image,(x,y+32));draw.text((x+8,y+8),name,fill='#0f172a')
 sheet.save(sheets/f'{group}.png')
manifest=[]
for path in sorted(root.glob('*.png')):
 with Image.open(path) as image:size=list(image.size)
 manifest.append({'file':path.name,'dimensions':size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'mtime':path.stat().st_mtime})
(root/'screenshot-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
items=''.join(f'<article><a href="{html.escape(item["file"])}"><img loading="lazy" src="{html.escape(item["file"])}" alt="{html.escape(item["file"])}"><p>{html.escape(item["file"])}</p></a></article>' for item in manifest)
(root/'index.html').write_text('<!doctype html><html lang="it"><meta charset="utf-8"><title>Supplier Ledger - evidenze Chromium</title><style>body{font:15px system-ui;background:#0c1018;color:#f4f7fb;margin:24px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:20px}article{padding:12px;border:1px solid #344055;border-radius:12px;background:#151b29}img{width:100%;height:auto}a{color:#c4b5fd;text-decoration:none}p{overflow-wrap:anywhere}</style><h1>Supplier Ledger - evidenze Chromium</h1><p>Screenshot dell\'app realmente renderizzata con fixture isolate. I dati dimostrativi non rappresentano il database reale. Clicca per aprire l\'originale.</p><main>'+items+'</main></html>',encoding='utf-8')
(root/'SCREENSHOTS.md').write_text('# Screenshot Chromium\n\nDati di test isolati; file originali senza immagini generate.\n\n'+'\n'.join(f'- [{item["file"]}](<{item["file"]}>) - {item["dimensions"][0]} x {item["dimensions"][1]}' for item in manifest)+'\n',encoding='utf-8')
print(json.dumps({'screenshots':len(manifest),'sheets':len(groups)}))
