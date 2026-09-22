from pathlib import Path
import re, html, json

root=Path(__file__).parent
index=(root/'index.html').read_text()
app=(root/'app.js').read_text()
# Extract simple catalog ids/titles/categories from source so route pages get unique head metadata.
items=[]
for m in re.finditer(r"\{id:'([^']+)',cat:'([^']+)',icon:'([^']+)',title:'([^']+)',desc:'([^']+)'", app):
    items.append(m.groups())
cat_names={
'dinheiro':'Dinheiro','casa':'Casa & Construção','carro':'Carro & Viagem','tempo':'Tempo & Datas','medidas':'Medidas & Conversores','cozinha':'Cozinha','festas':'Festas & Eventos','trabalho':'Trabalho & Rotina','outros':'Outras utilidades'}

for iid,cat,icon,title,desc in items:
    p=root/'ferramenta'/iid
    p.mkdir(parents=True,exist_ok=True)
    doc=index
    doc=doc.replace('<title>Resolvei — Ferramentas úteis para o dia a dia</title>',f'<title>{html.escape(title)} | Resolvei</title>')
    doc=re.sub(r'<meta name="description" content="[^"]*">', f'<meta name="description" content="{html.escape(desc)}">', doc, count=1)
    doc=re.sub(r'<link rel="canonical" href="[^"]*">', f'<link rel="canonical" href="https://resolvei.com.br/ferramenta/{iid}/">', doc, count=1)
    (p/'index.html').write_text(doc)
for cid,cname in cat_names.items():
    tools_in=[x for x in items if x[1]==cid]
    desc=f'Ferramentas de {cname.lower()} para cálculos, conversões e utilidades do dia a dia.'
    p=root/'categoria'/cid
    p.mkdir(parents=True,exist_ok=True)
    doc=index
    doc=doc.replace('<title>Resolvei — Ferramentas úteis para o dia a dia</title>',f'<title>{html.escape(cname)} | Resolvei</title>')
    doc=re.sub(r'<meta name="description" content="[^"]*">', f'<meta name="description" content="{html.escape(desc)}">', doc, count=1)
    doc=re.sub(r'<link rel="canonical" href="[^"]*">', f'<link rel="canonical" href="https://resolvei.com.br/categoria/{cid}/">', doc, count=1)
    (p/'index.html').write_text(doc)
