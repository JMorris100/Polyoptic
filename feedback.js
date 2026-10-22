/* Feedback bubble — a purple circle in the bottom-right corner that opens a
   short note asking for feedback. Self-contained: brings its own styles.
   Sits below the explorer's guide, drawers and mobile panels (z-index 55).

   The note opens by itself at most once per reader, and never on a phone,
   where it would cover the chart: on their second page, or after 45 seconds
   on the first, whichever comes first. After that only the circle shows. */
(function(){
  if(window.__pofb) return; window.__pofb=1;
  var EMAIL="josh.morris@smartmomos.co.uk";
  var KEY="polyoptic-feedback-seen", VIEWS="polyoptic-feedback-views";
  var seen=false, views=1;
  try{
    seen=localStorage.getItem(KEY)==="1";
    views=(parseInt(localStorage.getItem(VIEWS),10)||0)+1;
    if(!seen) localStorage.setItem(VIEWS,String(views));
  }catch(e){}

  var css=
  ".pofb{position:fixed;right:20px;bottom:20px;z-index:55;font-family:\"IBM Plex Sans\",system-ui,sans-serif;"+
    "display:flex;flex-direction:column;align-items:flex-end;gap:12px;pointer-events:none}"+
  ".pofb>*{pointer-events:auto}"+
  ".pofb-btn{width:52px;height:52px;border-radius:50%;border:0;padding:0;cursor:pointer;background:#4633A8;color:#fff;"+
    "display:grid;place-items:center;box-shadow:0 6px 18px rgba(20,12,60,.28);transition:transform .15s,background .15s}"+
  ".pofb-btn:hover{background:#3A2A8C;transform:scale(1.06)}"+
  ".pofb-btn:focus-visible,.pofb-x:focus-visible,.pofb-copy:focus-visible,.pofb-card a:focus-visible{outline:2px solid #fff;outline-offset:2px;box-shadow:0 0 0 4px #4633A8}"+
  ".pofb-btn svg{width:24px;height:24px}"+
  ".pofb-card{position:relative;width:min(300px,calc(100vw - 40px));background:#4633A8;color:#fff;border-radius:18px;"+
    "padding:18px 40px 18px 18px;font-size:14px;line-height:1.5;box-shadow:0 12px 32px rgba(20,12,60,.3);"+
    "transform-origin:bottom right;animation:pofb-in .22s ease-out}"+
  ".pofb-card[hidden]{display:none}"+
  ".pofb-card:after{content:\"\";position:absolute;right:20px;bottom:-7px;width:14px;height:14px;background:#4633A8;transform:rotate(45deg);border-radius:2px}"+
  ".pofb-card p{margin:0}"+
  ".pofb-card p+p{margin-top:8px}"+
  ".pofb-card b{font-weight:700}"+
  ".pofb-card a{color:#fff;font-weight:600;text-decoration:underline;text-underline-offset:2px;overflow-wrap:anywhere}"+
  ".pofb-mail{margin-top:12px;display:flex;flex-wrap:wrap;align-items:center;gap:8px 10px}"+
  ".pofb-copy{font:600 12px/1 \"IBM Plex Sans\",system-ui,sans-serif;color:#fff;background:rgba(255,255,255,.14);"+
    "border:1px solid rgba(255,255,255,.35);border-radius:100px;padding:6px 11px;cursor:pointer;white-space:nowrap}"+
  ".pofb-copy:hover{background:rgba(255,255,255,.26)}"+
  ".pofb-x{position:absolute;top:8px;right:8px;width:28px;height:28px;border-radius:50%;border:0;padding:0;cursor:pointer;"+
    "background:rgba(255,255,255,.14);color:#fff;display:grid;place-items:center}"+
  ".pofb-x:hover{background:rgba(255,255,255,.26)}"+
  ".pofb-x svg{width:14px;height:14px}"+
  "@keyframes pofb-in{from{opacity:0;transform:translateY(6px) scale(.96)}to{opacity:1;transform:none}}"+
  "@media (max-width:640px){.pofb{right:16px;bottom:16px}.pofb-btn{width:46px;height:46px}.pofb-btn svg{width:21px;height:21px}}"+
  "@media print{.pofb{display:none}}"+
  "@media (prefers-reduced-motion:reduce){.pofb-card{animation:none}.pofb-btn{transition:none}}";

  function init(){
    var st=document.createElement("style"); st.textContent=css; document.head.appendChild(st);

    var box=document.createElement("div"); box.className="pofb";
    box.innerHTML=
      '<div class="pofb-card" id="pofb-card" role="dialog" aria-label="Feedback" hidden>'+
        '<button class="pofb-x" type="button" aria-label="Close">'+
          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg></button>'+
        '<p><b>Hi, I’m Josh. I build Polyoptic.</b></p>'+
        '<p>Spotted a figure that looks wrong, a dataset you’d like added, or something that could work better? I’d love to hear it.</p>'+
        '<div class="pofb-mail"><a href="mailto:'+EMAIL+'?subject=Polyoptic%20feedback">'+EMAIL+'</a>'+
        '<button class="pofb-copy" type="button">Copy email</button></div>'+
      '</div>'+
      '<button class="pofb-btn" type="button" aria-label="Send feedback" aria-controls="pofb-card" aria-expanded="false">'+
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'+
        '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.9A8 8 0 1 1 21 12z"/><path d="M8.5 12h.01M12 12h.01M15.5 12h.01" stroke-width="2.6"/></svg></button>';
    document.body.appendChild(box);

    var card=box.querySelector(".pofb-card"), btn=box.querySelector(".pofb-btn"),
        x=box.querySelector(".pofb-x"), copy=box.querySelector(".pofb-copy");
    function show(open){
      card.hidden=!open; btn.setAttribute("aria-expanded",open?"true":"false");
      if(!open){try{localStorage.setItem(KEY,"1");}catch(e){}}
    }
    btn.addEventListener("click",function(){show(card.hidden);});
    x.addEventListener("click",function(){show(false);btn.focus();});
    document.addEventListener("keydown",function(e){if(e.key==="Escape"&&!card.hidden)show(false);});

    // A mailto link does nothing for people on webmail, so offer the address to paste.
    var tick;
    copy.addEventListener("click",function(){
      function done(ok){
        copy.textContent=ok?"Copied":"Press Ctrl+C";
        clearTimeout(tick); tick=setTimeout(function(){copy.textContent="Copy email";},2000);
      }
      function fallback(){
        var r=document.createRange(); r.selectNodeContents(box.querySelector(".pofb-mail a"));
        var s=getSelection(); s.removeAllRanges(); s.addRange(r);
        var ok=false; try{ok=document.execCommand("copy");}catch(e){}
        done(ok);
      }
      if(navigator.clipboard&&window.isSecureContext)
        navigator.clipboard.writeText(EMAIL).then(function(){done(true);},fallback);
      else fallback();
    });

    // The explorer's getting-started guide uses the same corner, so wait for
    // it to be closed first.
    function hello(){
      if(document.querySelector(".guide.on")){setTimeout(hello,1500);return;}
      if(!card.hidden) return;
      show(true);
      try{localStorage.setItem(KEY,"1");}catch(e){}
    }
    var phone=window.matchMedia&&matchMedia("(max-width:640px)").matches;
    if(!seen&&!phone) setTimeout(hello,views>=2?4000:45000);
  }
  if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",init); else init();
})();
