(() => {
  const PIX_KEY = "74bda51d-f08c-46ee-9dbb-464d79f8a344";
  const PIX_PAYLOAD = "00020126360014BR.GOV.BCB.PIX0114" + PIX_KEY + "5204000053039865802BR5910RESOLVEI6006CUIABA62070503***6304";
  // QR rendering is provided by the public QR image endpoint; the Pix key itself remains visible/copyable.
  const qrUrl = "https://api.qrserver.com/v1/create-qr-code/?size=320x320&margin=12&data=" + encodeURIComponent(PIX_PAYLOAD);

  function openDonation(){
    const modal=document.getElementById("donationModal");
    if(!modal)return;
    const img=document.getElementById("donationQr");
    if(img) img.src=qrUrl;
    modal.classList.add("open");
    modal.setAttribute("aria-hidden","false");
  }
  function closeDonation(){
    const modal=document.getElementById("donationModal");
    if(!modal)return;
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden","true");
  }
  async function copyPix(){
    try{
      await navigator.clipboard.writeText(PIX_KEY);
    }catch(e){
      const ta=document.createElement("textarea");
      ta.value=PIX_KEY; ta.style.position="fixed"; ta.style.opacity="0";
      document.body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove();
    }
    const btn=document.getElementById("copyPixBtn");
    if(btn){
      const old=btn.textContent; btn.textContent="✓ Chave copiada!";
      setTimeout(()=>btn.textContent=old,1800);
    }
  }
  document.addEventListener("click",(e)=>{
    const open=e.target.closest("[data-donation-open]");
    if(open){e.preventDefault();openDonation();return;}
    const close=e.target.closest("[data-donation-close]");
    if(close){e.preventDefault();closeDonation();return;}
    if(e.target.id==="donationModal")closeDonation();
    if(e.target.closest("#copyPixBtn"))copyPix();
  });
  document.addEventListener("keydown",(e)=>{if(e.key==="Escape")closeDonation();});
})();