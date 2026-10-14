export default function(component) {
  const {data,parentElement}=component;
  // getRandomValues also supports local HTTP test origins; never use weak random IDs.
  function uuid() {
    if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
    const bytes=crypto.getRandomValues(new Uint8Array(16));
    bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
    const hex=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
    return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
  }
  const key=data.participant_id+':'+data.period;
  window.__v5consult=window.__v5consult||{};
  let state=window.__v5consult[key];
  if (!state) {
    state={tab:uuid(),queue:[],busy:false,attached:false,open:false,token:data.token};
    window.__v5consult[key]=state;
    state.send=async function() {
      if(state.busy)return;
      state.busy=true;
      while(state.queue.length) {
        try {
          const response=await fetch('/study-events/v5',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(state.queue[0]),keepalive:true});
          if(!response.ok) {state.failed=true;break;}
          const event=state.queue.shift();
          if(event.action==='attach')state.attached=true;
          if(event.action==='paper_open')state.open=true;
          if(event.action==='paper_close')state.open=false;
          state.failed=false;
        } catch(error) {state.failed=true;break;}
      }
      state.busy=false;state.render?.();
    };
    state.enqueue=function(action) {state.queue.push({token:state.token,tab:state.tab,action,client_event_id:uuid()});state.send();};
    state.enqueue('attach');
    state.timer=setInterval(()=>{if(!state.queue.length)state.enqueue('heartbeat');else state.send();},10000);
    state.unload=()=>{const event={token:state.token,tab:state.tab,action:'unload',client_event_id:uuid()};navigator.sendBeacon('/study-events/v5',new Blob([JSON.stringify(event)],{type:'application/json'}));};
    window.addEventListener('pagehide',state.unload);
  }
  const button=document.createElement('button');button.type='button';button.style='min-height:44px;padding:10px 14px;font:inherit;cursor:pointer';
  const status=document.createElement('p');status.setAttribute('role','status');
  const panel=document.createElement('section');panel.setAttribute('aria-label','Full assigned research paper');
  const modes=document.createElement('select');modes.setAttribute('aria-label','Paper presentation');
  for(const name of ['Readable full text','PDF']){const opt=document.createElement('option');opt.textContent=name;modes.append(opt);}
  const body=document.createElement('div');panel.append(modes,body);
  function display(){body.replaceChildren();if(modes.value==='PDF'){const frame=document.createElement('iframe');frame.title=data.title;frame.src=data.pdf_data;frame.style='width:100%;height:620px;border:1px solid #aab';body.append(frame);}else{const pre=document.createElement('pre');pre.textContent=data.text;pre.style='white-space:pre-wrap;overflow-wrap:anywhere;font:16px/1.5 system-ui;max-height:620px;overflow:auto';body.append(pre);}}
  modes.onchange=display;display();
  state.render=()=>{button.textContent=state.open?'Close full paper and return to chat':'Open full research paper';button.disabled=!state.attached||state.queue.some(e=>e.action==='paper_open'||e.action==='paper_close');panel.hidden=!state.open;status.textContent=state.failed?'Paper logging connection interrupted. Retrying; this will not be treated as zero consultation.':'';};
  button.onclick=()=>{state.enqueue(state.open?'paper_close':'paper_open');state.render();};
  parentElement.replaceChildren(button,status,panel);state.render();
  // Rerenders retain state. A document refresh creates a new tab instance and restores closed.
  return ()=>{state.render=null;};
}
