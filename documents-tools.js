(function(){
  const documentTools = [
    {id:"pdfa",cat:"contabilidade",icon:"🗃️",title:"PDF/A — arquivamento",desc:"Converta PDFs para PDF/A e confira se o arquivo resultante abre corretamente.",tags:"pdfa pdf-a arquivo arquivamento contabilidade documento"},
    {id:"ocr-documentos",cat:"contabilidade",icon:"🔎",title:"OCR — texto pesquisável",desc:"Reconheça texto em PDFs digitalizados e imagens e exporte para TXT.",tags:"ocr reconhecer texto pdf imagem digitalizado contabilidade"},
    {id:"pdf-tabelas-excel",cat:"contabilidade",icon:"📊",title:"PDF para Excel — tabelas",desc:"Extraia tabelas de PDFs para XLSX com conteúdo organizado para revisão.",tags:"pdf excel xlsx tabela extrair extrato contabilidade"},
    {id:"comparar-documentos",cat:"contabilidade",icon:"⚖️",title:"Comparar documentos",desc:"Compare dois PDFs, DOCX, TXT ou CSV e identifique diferenças no texto.",tags:"comparar documentos pdf docx diferenças divergências contabilidade"}
  ];
  CATS.contabilidade={name:"Contabilidade e Documentos",icon:"🧾",desc:"Ferramentas para organizar, extrair e conferir documentos profissionais."};
  for(const t of documentTools) if(!tools.some(x=>x.id===t.id)) tools.push(t);

  const oldToolUI=toolUI;
  toolUI=function(id){ if(documentTools.some(t=>t.id===id)) return documentToolUI(id); return oldToolUI(id); };
  const oldBind=bind;
  bind=function(){ oldBind(); const rid=location.pathname.match(/ferramenta\/([^/]+)/)?.[1] || location.hash.match(/ferramenta\/([^?]+)/)?.[1]; if(documentTools.some(t=>t.id===rid)) bindDocumentTool(rid); };

  function documentToolUI(id){
    const cfg={
      pdfa:{title:"Converter para PDF/A",desc:"PDF/A é um formato de PDF voltado ao arquivamento de longo prazo.",accept:".pdf",multiple:false,button:"Converter e verificar"},
      "ocr-documentos":{title:"OCR — reconhecer texto",desc:"PDFs com texto digital podem ser extraídos diretamente. Para documentos digitalizados, o servidor precisa ter OCR instalado.",accept:".pdf,.png,.jpg,.jpeg,.tif,.tiff,.webp,.bmp",multiple:false,button:"Extrair texto"},
      "pdf-tabelas-excel":{title:"Extrair tabelas de PDF para Excel",desc:"As tabelas detectadas serão colocadas em XLSX. Sempre confira números, separadores decimais e cabeçalhos antes de usar os dados.",accept:".pdf",multiple:false,button:"Gerar Excel"},
      "comparar-documentos":{title:"Comparar dois documentos",desc:"Compare o texto extraível de dois arquivos e baixe um relatório com as diferenças.",accept:".pdf,.docx,.txt,.csv",multiple:true,button:"Comparar documentos"}
    }[id];
    return '<div class="document-tool-layout"><section class="card panel"><div class="eyebrow">DOCUMENTOS PROFISSIONAIS</div><h2>'+cfg.title+'</h2><p>'+cfg.desc+'</p><div class="field full"><label for="documentFiles">'+(id==="comparar-documentos"?"Selecione os dois documentos":"Selecione o arquivo")+'</label><input id="documentFiles" type="file" accept="'+cfg.accept+'" '+(cfg.multiple?'multiple':'')+'><small>'+(id==="comparar-documentos"?"Escolha exatamente dois arquivos, na ordem em que deseja comparar.":"Processamento temporário; os arquivos não são salvos na conta.")+'</small></div><div id="documentFileList" class="document-file-list">Nenhum arquivo selecionado.</div><div class="actions"><button class="btn primary" id="documentRunBtn" disabled>'+cfg.button+'</button><button class="btn ghost" id="documentResetBtn" type="button">Limpar</button></div><div id="documentStatus" class="notice">Selecione um arquivo para começar.</div><div class="notice"><strong>Privacidade:</strong> o arquivo é processado em diretório temporário e removido ao final da requisição. Evite enviar documentos que não tenha autorização para processar.</div></section><section id="documentResult"><div class="result-box"><div class="result-label">Resultado</div><div class="result-main">—</div><p>O resultado aparecerá aqui.</p></div></section></div>';
  }

  function bindDocumentTool(id){
    const input=document.getElementById("documentFiles"),run=document.getElementById("documentRunBtn"),reset=document.getElementById("documentResetBtn"),status=document.getElementById("documentStatus"),list=document.getElementById("documentFileList"),result=document.getElementById("documentResult");
    if(!input||!run)return;
    const update=()=>{
      const files=[...input.files||[]];
      list.innerHTML=files.length?files.map((f,i)=>'<div class="document-file-row"><span>'+(i+1)+'.</span><strong>'+escapeHtml(f.name)+'</strong><small>'+formatMB(f.size)+'</small></div>').join(""):"Nenhum arquivo selecionado.";
      const valid=id==="comparar-documentos"?files.length===2:files.length===1;
      run.disabled=!valid;
      status.textContent=valid?"Pronto para processar.":"Selecione "+(id==="comparar-documentos"?"exatamente dois arquivos.":"um arquivo.");
    };
    input.addEventListener("change",update);
    run.addEventListener("click",async()=>{
      const files=[...input.files||[]]; if(run.disabled)return;
      run.disabled=true;status.textContent="⏳ Processando arquivo(s). Aguarde...";
      try{
        const fd=new FormData();
        if(id==="comparar-documentos") files.forEach(f=>fd.append("files",f)); else fd.append("file",files[0]);
        const endpoint={pdfa:"/api/documents/pdfa","ocr-documentos":"/api/documents/ocr","pdf-tabelas-excel":"/api/documents/tables","comparar-documentos":"/api/documents/compare"}[id];
        const response=await fetch(endpoint,{method:"POST",body:fd});
        if(!response.ok){let data={};try{data=await response.json()}catch{}throw new Error(data.detail||"Não foi possível processar o documento.");}
        const blob=await response.blob(),disposition=response.headers.get("content-disposition")||"",match=disposition.match(/filename="?([^"]+)"?/i),name=match?match[1]:"resolvei-documento";
        const url=URL.createObjectURL(blob);
        result.innerHTML='<div class="result-box"><div class="result-label">Processamento concluído</div><div class="result-main">✓</div><p>'+escapeHtml(name)+'</p><div class="actions"><a class="btn primary" href="'+url+'" download="'+escapeHtml(name)+'">Baixar resultado</a></div></div>';
        status.textContent="✅ Concluído. Confira o arquivo antes de utilizá-lo profissionalmente.";
        const a=document.createElement("a");a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);
      }catch(error){status.textContent="⚠️ "+(error.message||"Falha no processamento.");}
      finally{run.disabled=false;}
    });
    reset.addEventListener("click",()=>{input.value="";update();result.innerHTML='<div class="result-box"><div class="result-label">Resultado</div><div class="result-main">—</div><p>O resultado aparecerá aqui.</p></div>';});
  }
  function escapeHtml(value){return String(value).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
  function formatMB(bytes){return (bytes/1024/1024).toLocaleString("pt-BR",{maximumFractionDigits:2})+" MB";}
  // app.js já executou por causa de defer; injeta os novos cards e redesenha a rota atual.
  if(typeof render==="function") render();
})();
