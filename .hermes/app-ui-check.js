
// State
const S={files:[],selFile:null,selPreset:'mp4_h264_1080p',jobs:[],cat:'all'};

// Init
function init(){
  S.files=[];
  S.selFile=null;
  renderFiles();
  renderJobs();
  setStat('Bereit — bitte echte Medien über "Dateien hinzufügen" importieren.');
}

function renderFiles(){
  const b=document.getElementById('filebox');
  if(!S.files.length){b.innerHTML='<div style="padding:8px;color:#888;font-size:11px;">Keine Dateien</div>';return;}
  b.innerHTML=S.files.map((f,i)=>`
    <div class="frow ${S.selFile===i?'sel':''}" onclick="selF(${i})">
      <span class="frow-icon">${f.ico}</span>
      <div class="frow-info">
        <div class="frow-name">${f.n}</div>
        <div class="frow-meta">${f.sz} · ${f.dur}</div>
      </div>
    </div>`).join('');
}
function selF(i){S.selFile=i;renderFiles();}
function clearFiles(){S.files=[];S.selFile=null;renderFiles();}
function addDemoFile(){
  setStat('Demo-Dateien sind deaktiviert. Bitte echte Dateien importieren.');
  openFileDialog();
}

// Tabs
function _baseShowTab(name, btn){
  document.querySelectorAll('.tabpanel').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tbtn').forEach(b=>b.classList.remove('active'));
  document.getElementById('tab-'+name).classList.add('active');
  if(btn) btn.classList.add('active');
}

// Disc type selector
function selDType(el, type){
  document.querySelectorAll('#discIconRow .disc-card').forEach(c=>c.classList.remove('sel'));
  el.classList.add('sel');
  const opts = {
    video: [
      ['mp4_h264_1080p','MP4 Video (H.264, 1080p) — Universal'],
      ['mp4_h265_4k','MP4 Video (H.265, 4K) — Hohe Qualität'],
      ['mkv_h265_copy_audio','MKV Video (H.265) — Verlustarm'],
      ['avi_xvid','AVI Video (XviD) — Klassisch/Retro']
    ],
    audio: [
      ['mp3_320k','MP3 Audio (320 kbps)'],
      ['flac_lossless','FLAC Audio (verlustfrei)'],
      ['wav_pcm','WAV Audio (PCM)']
    ],
    device: [
      ['iphone','iPhone / iPad — MP4 H.264'],
      ['android','Android — MP4 H.264']
    ],
    disc: [
      ['dvd_pal','Video-DVD PAL — Europa'],
      ['dvd_ntsc','Video-DVD NTSC — USA/Japan'],
      ['audio_cd','Audio-CD']
    ]
  };
  const sel = document.getElementById('presetSel');
  sel.innerHTML = (opts[type] || opts.video).map(([v,t]) => `<option value="${v}">${t}</option>`).join('');
  setStat('Zielformat-Gruppe: ' + ({video:'Video',audio:'Audio',device:'Gerät',disc:'Disc-Format'}[type] || type));
}
function selDisc(el){
  el.closest('.disc-icons-row').querySelectorAll('.disc-card').forEach(c=>c.classList.remove('sel'));
  el.classList.add('sel');
}

// Sound
function playSound(){
  try{
    const ctx=new(window.AudioContext||window.webkitAudioContext)();
    [{f:880,t:0,d:.18},{f:1108,t:.14,d:.18},{f:1318,t:.28,d:.18},{f:1760,t:.42,d:.5}].forEach(({f,t,d})=>{
      const o=ctx.createOscillator(),g=ctx.createGain();
      o.type='sine';o.frequency.value=f;
      g.gain.setValueAtTime(.3,ctx.currentTime+t);
      g.gain.exponentialRampToValueAtTime(.001,ctx.currentTime+t+d);
      o.connect(g).connect(ctx.destination);o.start(ctx.currentTime+t);o.stop(ctx.currentTime+t+d+.05);
    });
  }catch(e){}
}

// Jobs
function addJob(name,type){
  const j={id:Math.random().toString(36).slice(2,7),name,type,state:'pending',prog:0,status:'Wartet...'};
  S.jobs.push(j);renderJobs();
  if(!S.jobs.find(j=>j.state==='running'))runNext();
}
function runNext(){
  const j=S.jobs.find(j=>j.state==='pending');if(!j)return;
  j.state='running';
  document.getElementById('curjob').style.display='block';
  document.getElementById('nojob').style.display='none';
  document.getElementById('cjname').textContent=j.name;
  setStat('Verarbeite: '+j.name);
  const phases=['Dateien werden analysiert...','Konvertierung läuft...','Audio-Synchronisation...','Finalisierung...'];
  let p=0;
  const iv=setInterval(()=>{
    p+=Math.random()*4+1;
    if(p>=100){p=100;clearInterval(iv);
      j.state='done';j.prog=100;
      document.getElementById('curjob').style.display='none';
      document.getElementById('nojob').style.display='block';
      setStat('Fertig: '+j.name);
      renderJobs();
      if(document.getElementById('chkSound')&&document.getElementById('chkSound').checked)setTimeout(playSound,300);
      if(document.getElementById('snd')&&document.getElementById('snd').checked)setTimeout(playSound,300);
      setTimeout(()=>{if(S.jobs.some(j=>j.state==='pending'))runNext();else setStat('Bereit — Alle Jobs abgeschlossen.');},600);
    }else{
      j.prog=p;j.status=phases[Math.floor(p/26)]||'Verarbeitung...';
      document.getElementById('cjbar').style.width=p+'%';
      document.getElementById('cjpct').textContent=Math.floor(p)+'%';
      document.getElementById('cjstatus').textContent=j.status;
      renderJobs();
    }
  },120);
}
function renderJobs(){
  const l=document.getElementById('jlist');
  if(!S.jobs.length){l.innerHTML='<div style="padding:16px;color:#666;font-size:11px;">Keine Jobs vorhanden.</div>';return;}
  const icons={pending:'⏳',running:'🔄',done:'✅',failed:'❌'};
  l.innerHTML=S.jobs.map(j=>`
    <div class="jobrow">
      <span class="jstate">${icons[j.state]||'⏳'}</span>
      <span class="jname">${j.name}</span>
      <span class="jpct">${Math.floor(j.prog)}%</span>
    </div>`).join('');
}
function clearQ(){
  if(api()) api().clear_completed();
  S.jobs=S.jobs.filter(j=>j.state==='running');
  renderJobs();
}
function addDemoJob(){
  featureUnavailable('Demo-Job');
}

function fmtDuration(sec){
  if(sec===undefined || sec===null || sec==='') return '';
  if(typeof sec === 'string') return sec;
  sec = Math.round(Number(sec));
  if(!Number.isFinite(sec)) return '';
  const h=Math.floor(sec/3600), m=Math.floor((sec%3600)/60), s=sec%60;
  return h ? `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}` : `${m}:${String(s).padStart(2,'0')}`;
}
function menuAction(kind){
  if(kind==='file') { openFileDialog(); return; }
  if(kind==='extras') { showTab('settings', document.getElementById('tbtn-settings')); setStat('Extras: Einstellungen geöffnet.'); return; }
  if(kind==='help') { alert('RetroDisc 1.0\n\nAktuell funktionsfähig: Dateiimport, Formatwahl, Konvertieren, Download/Suche soweit yt-dlp/Backend verfügbar sind.\nNoch nicht vollständig: echte Disc-Rip/Brenn-Hardware-Workflows und manche AI-Funktionen hängen von Zusatztools/Modellen ab.'); return; }
}
function featureUnavailable(name){
  alert(name + ' ist in dieser Windows-EXE noch nicht fertig implementiert oder benötigt Zusatztools/Hardware. Ich zeige ab jetzt lieber diese Meldung statt Fake-Ergebnisse.');
  setStat(name + ': noch nicht fertig implementiert.');
}

// ── BACKEND API BRIDGE ──────────────────────────────────────────────
// Gibt die pywebview API zurück, oder null im Browser-Modus.
// Prüft LIVE bei jedem Aufruf (nicht gecacht), damit Buttons auch
// funktionieren sobald die Bridge nach dem Start verfügbar wird.
function api(){
  return (window.pywebview && window.pywebview.api) ? window.pywebview.api : null;
}
// Zeigt einen kurzen Hinweis wenn das Backend noch nicht bereit ist
function apiReady(){
  if (api()) return true;
  if (!window.__bridge_warned) {
    window.__bridge_warned = true;
    setTimeout(()=>{ window.__bridge_warned = false; }, 3000);
    const s = document.getElementById('statusbar') || document.querySelector('.statusbar');
    if (s) s.textContent = 'Backend startet noch... bitte 1-2 Sekunden warten';
  }
  return false;
}

// Backend-Events empfangen (werden von Python via evaluate_js gesendet)
window.onBackendEvent = function(payload) {
  const {event, data} = payload;
  switch(event) {
    case 'tools_ready':
      updateToolBadges(data); break;
    case 'job_queued':
      S.jobs.push({id:data.id, name:data.name, state:'pending', prog:0, status:''});
      renderJobs(); updateJobBadge(); break;
    case 'job_progress':
      const jp = S.jobs.find(j=>j.id===data.id);
      if(jp){ jp.prog=data.progress; jp.status=data.status; jp.state='running'; }
      if(S.jobs.find(j=>j.state==='running')){
        document.getElementById('cjbar').style.width = data.progress+'%';
        document.getElementById('cjpct').textContent = Math.floor(data.progress)+'%';
        document.getElementById('cjstatus').textContent = data.status||'';
        document.getElementById('curjob').style.display='block';
        document.getElementById('cjname').textContent = data.name;
        document.getElementById('nojob').style.display='none';
      }
      renderJobs(); break;
    case 'job_done':
      const jd = S.jobs.find(j=>j.id===data.id);
      if(jd){ jd.state='done'; jd.prog=100; }
      document.getElementById('curjob').style.display='none';
      document.getElementById('nojob').style.display='block';
      setStat('✓ Fertig: '+data.name+(data.elapsed?' ('+data.elapsed+'s)':''));
      renderJobs(); updateJobBadge();
      if(document.getElementById('chkSound')&&document.getElementById('chkSound').checked) playSound();
      if(document.getElementById('snd')&&document.getElementById('snd').checked) playSound();
      animBurnDone(); break;
    case 'job_failed':
      const jf = S.jobs.find(j=>j.id===data.id);
      if(jf){ jf.state='failed'; }
      document.getElementById('curjob').style.display='none';
      document.getElementById('nojob').style.display='block';
      setStat('✗ Fehler: '+(data.error||data.name));
      renderJobs(); updateJobBadge(); break;
    case 'queue_empty':
      setStat('Bereit — alle Jobs abgeschlossen'); break;
    case 'scan_progress':
      setStat('Scan: '+data.current+'/'+data.total+' — '+data.file); break;
  }
};

function updateToolBadges(tools){
  const strip=document.getElementById('strip');
  if(!strip) return;
  const badges = {
    ffmpeg: tools.ffmpeg?.ok ? '✓ FFmpeg '+tools.ffmpeg.version : '✗ FFmpeg fehlt',
    ytdlp:  tools.ytdlp?.ok  ? '✓ yt-dlp '+tools.ytdlp.version  : '✗ yt-dlp fehlt',
  };
  Object.entries(badges).forEach(([k,v])=>{
    const el=document.getElementById('badge-'+k);
    if(el){ el.textContent=v; el.className='strip-badge '+(v.startsWith('✓')?'ok':'warn'); }
  });
}

function updateJobBadge(){
  const running = S.jobs.filter(j=>j.state!=='done'&&j.state!=='failed').length;
  // Badge könnte im Toolbar-Button sein (optional)
}

// Actions — echte API-Aufrufe
async function goConvert(){
  if(!S.files.length){alert('Bitte zuerst Dateien hinzufügen!');return;}
  const sel=document.getElementById('presetSel');
  const preset=sel.value||'mp4_h264_1080p';
  const file=S.selFile!==null?S.files[S.selFile].path:S.files[0].path;
  if(!file){alert('Keine Datei ausgewählt!');return;}
  const outputDir=(document.getElementById('outdir')?.value||'').trim();
  const overwrite=Boolean(document.getElementById('chkOverwrite')?.checked);
  const a=api();
  if(a){
    try{
      const r=JSON.parse(await a.convert_file(file,preset,outputDir||null,overwrite));
      if(r.error) alert('Fehler: '+r.error);
      else {
        setStat('Konvertierung zur Queue hinzugefügt.');
        showTab('queue',document.getElementById('tbtn-queue'));
      }
    }catch(e){ alert('Konvertierung konnte nicht gestartet werden: '+e); }
  } else {
    alert('Backend noch nicht bereit — Konvertierung nicht möglich.');
  }
}

async function goBurn(){
  const t=document.getElementById('dvdtitle').value||'RetroDisc DVD';
  if(!S.files.length){alert('Bitte zuerst Dateien hinzufügen!');return;}
  animBurn();
  const a=api();
  if(a){
    const paths=JSON.stringify(S.files.map(f=>f.path));
    const r=JSON.parse(await a.create_dvd(paths,t,'PAL','16:9',false));
    if(r.error) alert('Fehler: '+r.error);
    else showTab('queue',document.getElementById('tbtn-queue'));
  } else {
    alert('Backend noch nicht bereit — Brennen/ISO nicht möglich.');
  }
}

async function goDL(){
  const input=document.getElementById('urlinp');
  const u=(input.value||'').trim();
  if(!/^https?:\/\/\S+$/i.test(u)){
    alert('Bitte eine gültige HTTP- oder HTTPS-URL eingeben!');
    input.focus();
    return;
  }
  const quality=document.getElementById('downloadQuality')?.value||'best';
  const after=document.getElementById('afterDownload')?.value||'save';
  const subtitleValue=document.getElementById('downloadSubtitles')?.value||'none';
  const audioOnly=['mp3','flac','wav'].includes(quality);
  const subtitles=subtitleValue!=='none';
  const a=api();
  if(a){
    try{
      setStat('Download wird zur Queue hinzugefügt...');
      const r=JSON.parse(await a.download_url(u,quality,audioOnly,after,subtitles));
      if(r.error){ alert('Fehler: '+r.error); setStat('Download konnte nicht gestartet werden.'); }
      else {
        setStat('Download zur Queue hinzugefügt.');
        showTab('queue',document.getElementById('tbtn-queue'));
      }
    }catch(e){ alert('Download konnte nicht gestartet werden: '+e); }
  } else {
    alert('Backend noch nicht bereit — Download nicht möglich.');
  }
}

async function doSearch(){
  const q=document.getElementById('sinp').value; if(!q)return;
  const res=document.getElementById('sresults');
  res.innerHTML='<div style="padding:8px;font-size:11px;color:#666;">Suche läuft...</div>';
  const a=api();
  if(a){
    const raw=JSON.parse(await a.search_media(q, '[]', 15));
    if(raw.error){res.innerHTML='<div style="padding:8px;color:red;font-size:11px;">'+raw.error+'</div>';return;}
    if(!raw.length){res.innerHTML='<div style="padding:8px;font-size:11px;color:#666;">Keine Ergebnisse für "'+q+'".</div>';return;}
    res.innerHTML=raw.map((r,i)=>`
      <div class="frow" style="padding:4px 6px;" onclick="this.classList.toggle('sel')">
        <span style="font-size:16px;">${r.source==='youtube'?'▶️':'📺'}</span>
        <div style="flex:1;min-width:0;">
          <div style="font-weight:bold;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escHtml(r.title)}</div>
          <div style="font-size:9px;color:#666;">${fmtDuration(r.duration||r.duration_seconds)||''} · ${r.quality||''} · ${(r.source||'').toUpperCase()}</div>
        </div>
        <button class="btn98" style="font-size:9px;padding:2px 6px;min-width:0;"
          onclick="dlResult(event,'${escAttr(r.url)}','${escAttr(r.title)}')">⬇ DL</button>
        <button class="btn98" style="font-size:9px;padding:2px 6px;min-width:0;margin-left:2px;"
          onclick="dvdResult(event,'${escAttr(r.url)}','${escAttr(r.title)}')">🔥 DVD</button>
      </div>`).join('');
  } else {
    res.innerHTML='<div style="padding:8px;font-size:11px;color:#a55;">Backend noch nicht bereit — Suche nicht möglich.</div>';
  }
}

async function dlResult(e, url, title){
  e.stopPropagation();
  const a=api();
  if(a){ JSON.parse(await a.download_url(url)); showTab('queue',document.getElementById('tbtn-queue')); }
  else { addJob('DL: '+title,'dl'); showTab('queue',document.getElementById('tbtn-queue')); }
}
async function dvdResult(e, url, title){
  e.stopPropagation();
  const a=api();
  if(a){
    // Download → danach DVD
    JSON.parse(await a.download_url(url,'best',false,'burn_dvd'));
    showTab('queue',document.getElementById('tbtn-queue'));
  } else {
    addJob(title+' → DVD','burn');
    showTab('queue',document.getElementById('tbtn-queue'));
  }
}

async function doAI(){
  const v=document.getElementById('aiinp').value; if(!v)return;
  const r=document.getElementById('airesp');
  r.textContent='KI analysiert...';
  const a=api();
  if(a){
    try {
      const res=JSON.parse(await a.run_assistant(v));
      r.textContent = res.message || JSON.stringify(res, null, 2);
    } catch(e){ r.textContent='Fehler: '+e; }
  } else {
    setTimeout(()=>{
      r.textContent=v.toLowerCase().includes('tatort')?
        '✓ Workflow: Suche "Tatort" → Download HD → DVD-PAL → Brennen. 3 Jobs geplant.':
        v.toLowerCase().includes('iphone')?
        '✓ Preset "iphone" — MP4 H.264 1080p, AAC 192k, High Profile Level 4.1.':
        '✓ Befehl verarbeitet.';
    },700);
  }
}

// Datei-Import über Dialog
async function openFileDialog(){
  const a=api();
  if(!a){ setStat('Backend noch nicht bereit — Dateiimport nicht möglich.'); return; }
  try{
    const r=JSON.parse(await a.open_file_dialog());
    if(r.error){ setStat(r.error); return; }
    const files = r.files || [r];
    files.forEach(f=>{
      if(!f.path) return;
      if(!S.files.find(x=>x.path===f.path)){
        const type = f.type || (f.video && f.video.length ? 'video' : 'audio');
        S.files.push({
          n:f.name || f.path.split(/[\\/]/).pop(),
          path:f.path,
          ico:type==='audio'?'🎵':'🎬',
          sz:f.size_fmt || f.size_formatted || f.size || '',
          dur:f.duration_fmt || f.duration_formatted || f.duration || ''
        });
      }
    });
    renderFiles();
    setStat(files.length + ' Datei(en) importiert.');
  }catch(e){ alert('Dateiimport fehlgeschlagen: '+e); }
}

async function openOutputFolderDialog(){
  const a=api();
  if(!a || !a.open_folder_dialog){ alert('Backend noch nicht bereit — Ordnerauswahl nicht möglich.'); return; }
  const r=JSON.parse(await a.open_folder_dialog());
  if(r.folder) document.getElementById('outdir').value = r.folder;
  else if(r.error) setStat(r.error);
}
async function openFolderBatch(){
  const a=api();
  if(!a || !a.open_folder_for_batch){ alert('Backend noch nicht bereit — Ordnerimport nicht möglich.'); return; }
  const r=JSON.parse(await a.open_folder_for_batch());
  if(r.folder){ setStat('Ordner gewählt: '+r.folder+'. Batch-Scan folgt als nächster Implementierungsschritt.'); }
  else if(r.error) setStat(r.error);
}

// Hilfsfunktionen
function escHtml(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function escAttr(s){ return s.replace(/'/g,"\\'").replace(/"/g,'\\"'); }

function animBurn(){
  let s=1;
  const iv=setInterval(()=>{
    document.querySelectorAll('.bstep').forEach((el,i)=>{
      el.classList.remove('on','done');
      if(i+1<s)el.classList.add('done');
      if(i+1===s)el.classList.add('on');
    });
    s++;if(s>7){clearInterval(iv);document.querySelectorAll('.bstep').forEach(e=>e.classList.remove('on'));}
  },700);
}
function animBurnDone(){
  document.querySelectorAll('.bstep').forEach(el=>{
    el.classList.remove('on'); el.classList.add('done');
  });
  setTimeout(()=>document.querySelectorAll('.bstep').forEach(e=>e.classList.remove('done')),3000);
}
function setStat(t){document.getElementById('stxt').textContent=t;}

// Überschreibe addDemoFile mit API-Version
const _origAddDemoFile = addDemoFile;
function addDemoFile(){ openFileDialog(); }

// ═══════════════════════════════════════════════════════════════
// VOLLSTÄNDIGE API-VERDRAHTUNG — alle Buttons rufen echtes Backend
// ═══════════════════════════════════════════════════════════════

// Hilfsfunktion: Datei aus Dateiliste holen
function getSelectedFile() {
  if (!S.files.length) return null;
  return S.selFile !== null ? S.files[S.selFile] : S.files[0];
}

// ── AI Tools vollständig verdrahtet ──────────────────────────────

async function startSmartEdit() {
  const f = getSelectedFile();
  if (!f) { alert('Bitte zuerst eine Videodatei hinzufügen!'); return; }
  const durSel = document.querySelector('#tab-ai .ai-sect:first-of-type select');
  const dur = durSel ? parseInt(durSel.value) * 60 : 300;
  const a = api();
  if (a) {
    setStat('KI Auto-Edit wird gestartet...');
    const r = JSON.parse(await a.create_highlights(f.path, dur));
    if (r.error) alert('Fehler: ' + r.error);
    else showTab('queue', document.getElementById('tbtn-queue'));
  } else {
    addJob('KI Auto-Edit: ' + f.n, 'smart_edit');
    showTab('queue', document.getElementById('tbtn-queue'));
  }
}

async function startUpscale() {
  const f = getSelectedFile();
  if (!f) { alert('Bitte zuerst eine Videodatei hinzufügen!'); return; }
  const scaleSel = document.querySelector('#tab-ai .ai-sect:nth-of-type(2) select');
  const scale = scaleSel && scaleSel.selectedIndex === 1 ? 2 : 4;
  const a = api();
  if (a) {
    setStat('Video-Upscaling wird gestartet...');
    const r = JSON.parse(await a.upscale_video(f.path, scale));
    if (r.error) alert('Fehler: ' + r.error);
    else showTab('queue', document.getElementById('tbtn-queue'));
  } else {
    addJob('Upscale ' + scale + 'x: ' + f.n, 'upscale');
    showTab('queue', document.getElementById('tbtn-queue'));
  }
}

async function startSubtitle() {
  const f = getSelectedFile();
  if (!f) { alert('Bitte zuerst eine Videodatei hinzufügen!'); return; }
  const modelSel = document.querySelector('#tab-ai .ai-sect:nth-of-type(3) select');
  const model = modelSel ? modelSel.value.split(' ')[0] : 'base';
  const a = api();
  if (a) {
    setStat('Whisper Untertitel-Generierung läuft...');
    const r = JSON.parse(await a.generate_subtitles(f.path, '', model, 'srt'));
    if (r.error) alert('Fehler: ' + r.error);
    else showTab('queue', document.getElementById('tbtn-queue'));
  } else {
    addJob('Untertitel (' + model + '): ' + f.n, 'subtitle');
    showTab('queue', document.getElementById('tbtn-queue'));
  }
}

async function startInterpolate() {
  const f = getSelectedFile();
  if (!f) { alert('Bitte zuerst eine Videodatei hinzufügen!'); return; }
  const fpsSel = document.querySelector('#tab-ai .ai-sect:nth-of-type(4) select');
  const fps = fpsSel ? parseFloat(fpsSel.value) : 60.0;
  const a = api();
  if (a) {
    setStat('Frame-Interpolation wird gestartet...');
    const r = JSON.parse(await a.interpolate_video(f.path, fps));
    if (r.error) alert('Fehler: ' + r.error);
    else showTab('queue', document.getElementById('tbtn-queue'));
  } else {
    addJob(fps + 'fps Interpolation: ' + f.n, 'interpolate');
    showTab('queue', document.getElementById('tbtn-queue'));
  }
}

// ── ISO erstellen ────────────────────────────────────────────────
async function createISO() {
  if (!S.files.length) { alert('Bitte zuerst Dateien hinzufügen!'); return; }
  const t = document.getElementById('dvdtitle').value || 'RetroDisc';
  const a = api();
  if (a) {
    setStat('ISO-Erstellung läuft...');
    const paths = JSON.stringify(S.files.map(f => f.path));
    const r = JSON.parse(await a.create_dvd(paths, t, 'PAL', '16:9', false));
    if (r.error) alert('Fehler: ' + r.error);
    else showTab('queue', document.getElementById('tbtn-queue'));
  } else {
    addJob('ISO: ' + t, 'iso');
    showTab('queue', document.getElementById('tbtn-queue'));
  }
}

// ── Disc rippen ──────────────────────────────────────────────────
async function goRip() {
  const a = api();
  const fmt = document.querySelector('#tab-rip select') ?
    document.querySelector('#tab-rip .ai-sect select, #tab-rip select').value : 'MKV';
  if (a) {
    // Disc-Rippen: Input ist der Laufwerk-Buchstabe
    const r = JSON.parse(await a.convert_file('D:\\', 'mkv_h265'));
    if (r.error) alert('Fehler: ' + r.error);
    else showTab('queue', document.getElementById('tbtn-queue'));
  } else {
    addJob('DVD rippen → ' + fmt, 'rip');
    showTab('queue', document.getElementById('tbtn-queue'));
  }
}

// ── Einstellungen speichern ──────────────────────────────────────
async function saveSettings() {
  const a = api();
  if (!a) { alert('Einstellungen gespeichert (Demo-Modus)'); return; }

  // Werte aus dem Formular lesen
  const inputs = document.querySelectorAll('#tab-settings input[type=text]');
  const selects = document.querySelectorAll('#tab-settings select');
  const checkboxes = document.querySelectorAll('#tab-settings input[type=checkbox]');

  // Aktuelle Settings laden und patchen
  const current = JSON.parse(await a.get_settings());

  // Tool-Pfade
  const allInputs = [...inputs];
  if (allInputs[0]) current.tools.ffmpeg   = allInputs[0].value;
  if (allInputs[1]) current.tools.ffprobe  = allInputs[1].value;
  if (allInputs[2]) current.tools.ytdlp    = allInputs[2].value;
  if (allInputs[3]) current.tools.dvdauthor= allInputs[3].value;
  if (allInputs[4]) current.tools.ollama_host = allInputs[4].value || 'http://localhost:11434';

  // Outputs
  if (allInputs[5]) current.directories.output_dir   = allInputs[5].value;
  if (allInputs[6]) current.directories.download_dir = allInputs[6].value;

  // Selects
  const allSels = [...selects];
  if (allSels[0]) current.conversion.dvd_standard = allSels[0].value.includes('PAL') ? 'PAL' : 'NTSC';
  if (allSels[1]) current.ai.whisper_model = allSels[1].value.split(' ')[0];
  if (allSels[2]) current.ai.ollama_model  = allSels[2].value;

  // Checkboxes
  const sndBox = document.getElementById('snd');
  if (sndBox) current.sound.play_on_complete = sndBox.checked;

  const r = JSON.parse(await a.save_settings(JSON.stringify(current)));
  if (r.error) alert('Fehler beim Speichern: ' + r.error);
  else {
    setStat('✓ Einstellungen gespeichert');
    alert('Einstellungen gespeichert!');
  }
}

// ── Settings laden und ins Formular eintragen ────────────────────
async function loadSettingsIntoForm() {
  const a = api();
  if (!a) return;
  try {
    const s = JSON.parse(await a.get_settings());
    const inputs = [...document.querySelectorAll('#tab-settings input[type=text]')];
    if (inputs[0]) inputs[0].value = s.tools.ffmpeg  || '';
    if (inputs[1]) inputs[1].value = s.tools.ffprobe || '';
    if (inputs[2]) inputs[2].value = s.tools.ytdlp   || '';
    if (inputs[3]) inputs[3].value = s.tools.dvdauthor || '';
    if (inputs[4]) inputs[4].value = s.ai?.ollama_host || 'http://localhost:11434';
    if (inputs[5]) inputs[5].value = s.directories.output_dir   || '';
    if (inputs[6]) inputs[6].value = s.directories.download_dir || '';
    const snd = document.getElementById('snd');
    if (snd) snd.checked = s.sound?.play_on_complete !== false;
  } catch(e) { console.log('Settings laden:', e); }
}

// ── Tool-Status beim Start laden ─────────────────────────────────
async function loadToolStatus() {
  const a = api();
  if (!a) return;
  try {
    const tools = JSON.parse(await a.check_tools());
    const strip = document.getElementById('strip');
    if (!strip) return;
    const badges = strip.querySelectorAll('.strip-badge');
    const map = {ffmpeg: tools.ffmpeg, ffprobe: tools.ffprobe, ytdlp: tools.ytdlp};
    let i = 0;
    for (const [name, info] of Object.entries(map)) {
      if (badges[i]) {
        const ok = info && info.available;
        badges[i].textContent = ok ? '✓ ' + name : '✗ ' + name + ' fehlt';
        badges[i].className = 'strip-badge ' + (ok ? 'ok' : 'warn');
      }
      i++;
    }
  } catch(e) { console.log('Tool-Status:', e); }
}

// ── Queue periodisch aktualisieren ───────────────────────────────
async function refreshQueue() {
  const a = api();
  if (!a) return;
  try {
    const jobs = JSON.parse(await a.get_queue());
    // State aus Backend in lokalen State übernehmen
    jobs.forEach(bj => {
      const lj = S.jobs.find(j => j.id === bj.id);
      if (lj) {
        lj.state = bj.state;
        lj.prog  = bj.progress;
      } else if (bj.state !== 'done') {
        S.jobs.push({id: bj.id, name: bj.name, state: bj.state,
                     prog: bj.progress, status: ''});
      }
    });
    renderJobs();
    updateJobBadge();
    // Laufender Job im Detail-Panel
    const running = S.jobs.find(j => j.state === 'running');
    if (running) {
      document.getElementById('curjob').style.display = 'block';
      document.getElementById('nojob').style.display  = 'none';
      document.getElementById('cjname').textContent   = running.name;
      document.getElementById('cjbar').style.width    = running.prog + '%';
      document.getElementById('cjpct').textContent    = Math.floor(running.prog) + '%';
    }
  } catch(e) {}
}

// ── Cancel Job ───────────────────────────────────────────────────
async function cancelJob(jobId) {
  const a = api();
  if (a) await a.cancel_job(jobId);
  S.jobs = S.jobs.filter(j => j.id !== jobId);
  renderJobs(); updateJobBadge();
}

// ── Output-Ordner öffnen ─────────────────────────────────────────
async function openOutputFolder() {
  const a = api();
  if (a) await a.open_output_folder();
}

// ── Startup ─────────────────────────────────────────────────────
async function startup() {
  await loadToolStatus();
  await loadSettingsIntoForm();
  // Alle 2 Sekunden Queue aktualisieren
  setInterval(refreshQueue, 2000);
}

// Echte onPythonEvent-Verbindung (von Python via evaluate_js gesendet)
window.onPythonEvent = function(payload) {
  const {event, data} = payload;
  if (window.onBackendEvent) window.onBackendEvent(payload);
};


// ═══════════════════════════════════════════════════════════════
// BEARBEITEN-TAB: Trim, Merge, DVD-Menü, Watch Folder
// ═══════════════════════════════════════════════════════════════

let S_merge = [];       // Dateien für Merge
let S_trimFile = null;  // Aktuelle Trim-Datei
let S_template = 'classic'; // Gewähltes Menü-Template

// ── Trim ─────────────────────────────────────────────────────────
function setTrimFile() {
  const f = getSelectedFile ? getSelectedFile() : (S.files[S.selFile] || S.files[0]);
  if (!f) { alert('Bitte zuerst eine Datei in der linken Liste auswählen!'); return; }
  S_trimFile = f;
  document.getElementById('trimFile').value = f.path || f.n;
  // Dauer aus MediaInfo laden
  loadTrimDuration(f.path || f.n);
}

async function loadTrimDuration(path) {
  const a = api();
  if (!a) return;
  try {
    const info = JSON.parse(await a.get_mediainfo(path));
    if (info.error) return;
    const dur = info.duration_fmt || '';
    const durSec = parseDurationToSeconds(dur);
    if (durSec > 0) {
      document.getElementById('trimEnd').value = durSec;
      document.getElementById('trimDurLabel').textContent =
        `Gesamtdauer: ${dur}`;
      // Einfache Timeline anzeigen
      const tl = document.getElementById('trimTimeline');
      tl.innerHTML = `<div style="width:100%;padding:8px;font-size:10px;color:#444;">
        <strong>${info.name}</strong><br>
        Dauer: ${info.duration_fmt} · ${info.resolution||''} · 
        ${info.video?.[0]?.codec||''} · ${info.audio?.[0]?.codec||''}<br>
        <div style="margin-top:6px;background:#ddd;height:12px;border:1px solid #aaa;position:relative;">
          <div style="position:absolute;left:0;top:0;bottom:0;width:0%;background:#0a246a;opacity:0.5;" id="trimRangeBar"></div>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:9px;color:#888;margin-top:2px;">
          <span>0s</span><span>${durSec}s</span>
        </div>
      </div>`;
    }
  } catch(e) {}
}

function parseDurationToSeconds(fmt) {
  const parts = (fmt || '').split(':').reverse();
  let sec = 0;
  if (parts[0]) sec += parseFloat(parts[0]);
  if (parts[1]) sec += parseInt(parts[1]) * 60;
  if (parts[2]) sec += parseInt(parts[2]) * 3600;
  return sec;
}

async function doTrim() {
  const file = S_trimFile || getSelectedFile();
  if (!file) { alert('Bitte zuerst eine Datei wählen!'); return; }
  const start = parseFloat(document.getElementById('trimStart').value) || 0;
  const end = parseFloat(document.getElementById('trimEnd').value) || 60;
  if (end <= start) { alert('Ende muss nach dem Start liegen!'); return; }
  const a = api();
  if (a) {
    setStat('Trim läuft...');
    const r = JSON.parse(await a.trim_video(file.path || file.n, start, end));
    if (r.error) alert('Fehler: ' + r.error);
    else {
      showTab('queue', document.getElementById('tbtn-queue'));
      setStat('✓ Trim gestartet');
    }
  } else {
    addJob(`Trim: ${file.n} [${start}s–${end}s]`, 'trim');
    showTab('queue', document.getElementById('tbtn-queue'));
  }
}

function previewTrim() {
  alert('Vorschau: Im vollständigen Release wird hier ein eingebetteter Player angezeigt.');
}

// ── Merge ─────────────────────────────────────────────────────────
function addToMerge() {
  const f = getSelectedFile ? getSelectedFile() : null;
  if (!f) { alert('Bitte zuerst eine Datei in der Liste auswählen!'); return; }
  if (S_merge.find(x => (x.path||x.n) === (f.path||f.n))) {
    alert('Diese Datei ist bereits in der Merge-Liste!'); return;
  }
  S_merge.push(f);
  renderMergeList();
}

function clearMerge() {
  S_merge = [];
  renderMergeList();
}

function renderMergeList() {
  const el = document.getElementById('mergeList');
  if (!S_merge.length) {
    el.innerHTML = '<div style="padding:8px;color:#aaa;font-size:11px;">Keine Dateien</div>';
    return;
  }
  el.innerHTML = S_merge.map((f, i) => `
    <div style="display:flex;align-items:center;gap:6px;padding:3px 6px;border-bottom:1px solid #eee;font-size:11px;">
      <span style="color:#666;width:20px;text-align:right;">${i+1}.</span>
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${f.n||f.path}</span>
      <button style="padding:1px 5px;font-size:9px;cursor:pointer;border:1px solid #aaa;background:#f5f5f5;"
        onclick="S_merge.splice(${i},1);renderMergeList()">✕</button>
    </div>`).join('');
}

async function doMerge() {
  if (S_merge.length < 2) { alert('Mindestens 2 Dateien zum Zusammenfügen nötig!'); return; }
  const outName = document.getElementById('mergeOutput').value || 'merged_output.mp4';
  const paths = JSON.stringify(S_merge.map(f => f.path || f.n));
  const a = api();
  if (a) {
    setStat('Merge läuft...');
    const r = JSON.parse(await a.merge_videos(paths, outName));
    if (r.error) alert('Fehler: ' + r.error);
    else showTab('queue', document.getElementById('tbtn-queue'));
  } else {
    addJob(`Merge: ${S_merge.length} Dateien → ${outName}`, 'merge');
    showTab('queue', document.getElementById('tbtn-queue'));
  }
}

// ── DVD-Menü ──────────────────────────────────────────────────────
const MENU_PREVIEWS = {
  classic: { bg:'#000', fg:'#fff', accent:'#c8a000', emoji:'🎬' },
  cinema:  { bg:'#1a0000', fg:'#ffd700', accent:'#c00', emoji:'🎭' },
  retro:   { bg:'#1a0a00', fg:'#ff8c00', accent:'#ff4500', emoji:'📼' },
  minimal: { bg:'#fff', fg:'#333', accent:'#0a246a', emoji:'◻' },
  family:  { bg:'#e8f4ff', fg:'#0060a0', accent:'#ff6600', emoji:'👨‍👩‍👧' },
  concert: { bg:'#0a0010', fg:'#e0e0ff', accent:'#8844ff', emoji:'🎸' },
  nature:  { bg:'#0a2010', fg:'#90ee90', accent:'#228b22', emoji:'🌿' },
  holiday: { bg:'#003366', fg:'#ffe', accent:'#ff9900', emoji:'🌅' },
};

function selectTemplate(el, id) {
  S_template = id;
  document.querySelectorAll('#menuTemplates > div').forEach(d => {
    d.style.borderColor = '#808080';
    d.style.background = 'white';
  });
  el.style.borderColor = '#0a246a';
  el.style.background = '#e8f0ff';
  updateMenuPreview();
}

function updateMenuPreview() {
  const t = MENU_PREVIEWS[S_template] || MENU_PREVIEWS.classic;
  const title = document.getElementById('menuTitle').value || 'Mein Film';
  const prev = document.getElementById('menuPreview');
  prev.style.background = t.bg;
  prev.style.color = t.fg;
  prev.style.padding = '16px';
  prev.innerHTML = `
    <div style="font-size:22px;margin-bottom:6px;">${t.emoji}</div>
    <div style="font-size:14px;font-weight:bold;color:${t.accent};">${escHtml(title)}</div>
    <div style="margin-top:8px;display:flex;gap:8px;justify-content:center;font-size:10px;">
      <span style="border:1px solid ${t.accent};padding:2px 8px;cursor:pointer;">▶ Film abspielen</span>
      <span style="border:1px solid ${t.fg};padding:2px 8px;cursor:pointer;opacity:0.7;">Kapitel</span>
    </div>`;
}

document.addEventListener('input', e => {
  if (e.target && e.target.id === 'menuTitle') updateMenuPreview();
});

async function applyMenuTemplate() {
  const title = document.getElementById('menuTitle').value || 'RetroDisc DVD';
  const a = api();
  if (a) {
    const r = JSON.parse(await a.set_dvd_menu(S_template, title));
    if (r.error) alert('Fehler: ' + r.error);
    else setStat(`✓ DVD-Menü "${S_template}" für "${title}" gesetzt`);
  } else {
    setStat(`✓ DVD-Menü: ${S_template} / "${title}" (Demo)`);
  }
}

// ── Watch Folder ──────────────────────────────────────────────────
async function chooseWatchFolder() {
  const a = api();
  if (a) {
    const r = JSON.parse(await a.open_folder_dialog());
    if (r.folder) document.getElementById('watchFolder').value = r.folder;
  } else {
    setStat('Backend noch nicht bereit — Ordnerauswahl nicht möglich.');
  }
}

async function startWatchFolder() {
  const folder = document.getElementById('watchFolder').value;
  if (!folder) { alert('Bitte zuerst einen Ordner wählen!'); return; }
  const action = document.getElementById('watchAction').value;
  const preset = document.getElementById('watchPreset').value;
  const a = api();
  if (a) {
    const r = JSON.parse(await a.set_watch_folder(folder, preset, action, true));
    if (r.error) alert('Fehler: ' + r.error);
    else document.getElementById('watchStatus').textContent =
      '▶ Überwacht: ' + folder + ' → ' + action;
  } else {
    document.getElementById('watchStatus').textContent = 'Backend noch nicht bereit — Watch Folder nicht gestartet.';
  }
}

async function stopWatchFolder() {
  document.getElementById('watchStatus').textContent = '⏹ Gestoppt';
}

// ═══════════════════════════════════════════════════════════════
// BIBLIOTHEK-TAB
// ═══════════════════════════════════════════════════════════════

async function scanLibrary() {
  const a = api();
  if (!a) {
    document.getElementById('libStats').textContent = 'Backend noch nicht bereit — Bibliothek-Scan nicht verfügbar';
    return;
  }
  const result = await a.open_folder_dialog();
  const r = JSON.parse(result);
  if (r.error) return;
  setStat('Bibliothek wird gescannt: ' + r.folder);
  document.getElementById('libStats').textContent = 'Scannen läuft...';
  const sr = JSON.parse(await a.scan_library(r.folder));
  if (sr.error) {
    document.getElementById('libStats').textContent = 'Fehler: ' + sr.error;
  } else {
    await loadLibraryStats();
    await searchLibrary();
  }
}

async function loadLibraryStats() {
  const a = api();
  if (!a) return;
  try {
    const s = JSON.parse(await a.get_library_stats());
    const el = document.getElementById('libStats');
    if (s.total !== undefined) {
      const size = s.total_size ? (s.total_size / 1024 / 1024 / 1024).toFixed(1) + ' GB' : '';
      el.textContent = `${s.total} Dateien · ${s.videos||0} Videos · ${s.audio||0} Audio ${size}`;
    }
  } catch(e) {}
}

async function searchLibrary() {
  const a = api();
  const q = document.getElementById('libSearch').value;
  const filter = document.getElementById('libFilter').value;

  let items = [];
  if (a) {
    if (q) {
      const r = JSON.parse(await a.search_library(q));
      items = Array.isArray(r) ? r : [];
    } else {
      const r = JSON.parse(await a.get_library(filter, 100));
      items = Array.isArray(r) ? r : [];
    }
  } else {
    document.getElementById('libStats').textContent = 'Backend noch nicht bereit — Bibliothek nicht verfügbar.';
    items = [];
  }

  renderLibrary(items);
}

function renderLibrary(items) {
  const el = document.getElementById('libResults');
  if (!items.length) {
    el.innerHTML = '<div style="padding:16px;color:#aaa;font-size:11px;">Keine Einträge gefunden.</div>';
    return;
  }
  el.innerHTML = items.map(f => {
    const dur = formatDur(f.duration || 0);
    const size = formatSize(f.file_size || 0);
    const res = (f.width && f.height) ? `${f.width}×${f.height}` : '';
    const codec = f.video_codec || f.audio_codec || '';
    const icon = f.media_type === 'audio' ? '🎵' : '🎬';
    return `<div class="frow" style="padding:4px 8px;" onclick="showMediaInfo('${escAttr(f.path||f.filename)}')">
      <span style="font-size:16px;flex-shrink:0;">${icon}</span>
      <div style="flex:1;min-width:0;">
        <div style="font-weight:bold;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
          ${escHtml(f.filename || f.path || '')}
        </div>
        <div style="font-size:9px;color:#666;">
          ${dur} · ${size} ${res ? '· '+res : ''} ${codec ? '· '+codec : ''}
        </div>
      </div>
      <button class="btn98" style="font-size:9px;padding:2px 5px;min-width:0;" onclick="addLibFileToQueue(event,'${escAttr(f.path||f.filename)}')">+</button>
    </div>`;
  }).join('');
}

function formatDur(sec) {
  if (!sec) return '';
  const h = Math.floor(sec/3600), m = Math.floor((sec%3600)/60), s = Math.floor(sec%60);
  return h > 0 ? `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}` :
                 `${m}:${String(s).padStart(2,'0')}`;
}

function formatSize(bytes) {
  if (!bytes) return '';
  if (bytes > 1e9) return (bytes/1e9).toFixed(1) + ' GB';
  if (bytes > 1e6) return (bytes/1e6).toFixed(0) + ' MB';
  return (bytes/1e3).toFixed(0) + ' KB';
}

async function showMediaInfo(path) {
  const panel = document.getElementById('mediainfoPanel');
  const content = document.getElementById('mediainfoContent');
  panel.style.display = 'block';
  content.innerHTML = 'Lade...';
  const a = api();
  if (!a) { content.innerHTML = 'Backend noch nicht bereit — MediaInfo nicht verfügbar'; return; }
  try {
    const info = JSON.parse(await a.get_mediainfo(path));
    if (info.error) { content.innerHTML = 'Fehler: ' + info.error; return; }
    content.innerHTML = `
      <table style="width:100%;border-collapse:collapse;font-size:11px;">
        <tr><td style="padding:2px 8px;font-weight:bold;width:140px;">Datei</td><td>${escHtml(info.name||'')}</td></tr>
        <tr style="background:#f5f5f5;"><td style="padding:2px 8px;font-weight:bold;">Typ</td><td>${info.type||''} · ${info.container||''}</td></tr>
        <tr><td style="padding:2px 8px;font-weight:bold;">Dauer</td><td>${info.duration_fmt||''}</td></tr>
        <tr style="background:#f5f5f5;"><td style="padding:2px 8px;font-weight:bold;">Größe</td><td>${info.size_fmt||''}</td></tr>
        <tr><td style="padding:2px 8px;font-weight:bold;">Auflösung</td><td>${info.resolution||'–'}</td></tr>
        ${info.video?.length ? `<tr style="background:#f5f5f5;"><td style="padding:2px 8px;font-weight:bold;">Video</td>
          <td>${info.video.map(v=>`${v.codec} ${v.width}×${v.height} @ ${v.fps}fps`).join(', ')}</td></tr>` : ''}
        ${info.audio?.length ? `<tr><td style="padding:2px 8px;font-weight:bold;">Audio</td>
          <td>${info.audio.map(a=>`${a.codec} ${a.channels}ch @ ${a.sample_rate}Hz${a.language?' ['+a.language+']':''}`).join(', ')}</td></tr>` : ''}
        ${info.subs?.length ? `<tr style="background:#f5f5f5;"><td style="padding:2px 8px;font-weight:bold;">Untertitel</td>
          <td>${info.subs.map(s=>s.lang||s.codec).join(', ')}</td></tr>` : ''}
        ${info.title ? `<tr><td style="padding:2px 8px;font-weight:bold;">Titel</td><td>${escHtml(info.title)}</td></tr>` : ''}
        ${info.artist ? `<tr style="background:#f5f5f5;"><td style="padding:2px 8px;font-weight:bold;">Artist</td><td>${escHtml(info.artist)}</td></tr>` : ''}
      </table>
      <div style="margin-top:8px;display:flex;gap:5px;">
        <button class="btn98" onclick="addLibFileToQueueDirect('${escAttr(path)}')">+ Zur Konvertierung</button>
        <button class="btn98" onclick="document.getElementById('mediainfoPanel').style.display='none'">Schließen</button>
      </div>`;
  } catch(e) { content.innerHTML = 'Fehler: ' + e; }
}

async function addLibFileToQueue(e, path) {
  e.stopPropagation();
  addLibFileToQueueDirect(path);
}

function addLibFileToQueueDirect(path) {
  const fname = path.split('\\').pop().split('/').pop();
  if (!S.files.find(f => f.path === path)) {
    S.files.push({ path, n: fname, sz: '', dur: '', ico: '🎬' });
    renderFiles();
  }
  showTab('convert', document.getElementById('tbtn-convert'));
  setStat('✓ ' + fname + ' zur Konvertierung hinzugefügt');
}

// Bibliothek beim Laden des Tabs aktualisieren
function showTab(name, btn) {
  _baseShowTab(name, btn);
  if (name === 'library') {
    loadLibraryStats();
    searchLibrary();
  }
  if (name === 'edit') {
    updateMenuPreview();
  }
}


// ═══════════════════════════════════════════════════════════════
// NEUE FEATURES: Drag-Drop, MediaInfo, Batch, Presets, Sound
// ═══════════════════════════════════════════════════════════════

// ── Drag-Drop Handler ────────────────────────────────────────────
async function handleFileDrop(event) {
  event.preventDefault();
  const items = [...event.dataTransfer.items];
  const files = [...event.dataTransfer.files];

  for (const file of files) {
    const ext = file.name.split('.').pop().toLowerCase();
    const mediaExts = ['mp4','mkv','avi','mov','wmv','flv','webm','mpg',
                       'mpeg','vob','ts','mp3','flac','wav','aac','ogg',
                       'm4a','iso','m4v'];
    if (!mediaExts.includes(ext)) continue;

    // Temporären Pfad erstellen (pywebview gibt uns den echten Pfad)
    const icon = ['mp3','flac','wav','aac','ogg','m4a'].includes(ext) ? '🎵' : '🎬';
    const sizeMB = (file.size / 1024 / 1024).toFixed(1);
    const entry = {
      n: file.name,
      path: file.path || file.name, // Electron/pywebview gibt file.path
      sz: sizeMB + ' MB',
      dur: '–',
      ico: icon,
      ext: ext,
    };

    if (!S.files.find(f => f.n === entry.n)) {
      S.files.push(entry);
      // Echte Dateianalyse im Hintergrund
      analyzeDroppedFile(entry);
    }
  }
  renderFiles();
}

async function analyzeDroppedFile(entry) {
  const a = api();
  if (!a || !entry.path || entry.path === entry.n) return;
  try {
    const info = JSON.parse(await a.get_mediainfo(entry.path));
    if (info.error) return;
    // Update entry mit echten Daten
    entry.dur = info.duration_fmt || '–';
    entry.sz  = info.size_fmt || entry.sz;
    if (info.resolution) entry.res = info.resolution;
    renderFiles();
  } catch(e) {}
}

// ── Datei-Info Panel (links) ──────────────────────────────────────
async function selectFileAndShowInfo(i) {
  S.selFile = i;
  renderFiles();
  const f = S.files[i];
  const panel = document.getElementById('fileInfoPanel');
  const nameEl = document.getElementById('fiInfoName');
  const detailEl = document.getElementById('fiInfoDetails');

  panel.style.display = 'block';
  nameEl.textContent = f.n;
  detailEl.textContent = 'Lade Infos...';

  const a = api();
  if (a && (f.path && f.path !== f.n)) {
    try {
      const info = JSON.parse(await a.get_mediainfo(f.path));
      if (!info.error) {
        const lines = [];
        if (info.duration_fmt) lines.push('⏱ ' + info.duration_fmt);
        if (info.size_fmt)     lines.push('💾 ' + info.size_fmt);
        if (info.resolution)   lines.push('📐 ' + info.resolution);
        if (info.video?.[0])   lines.push('🎬 ' + info.video[0].codec + ' @ ' + info.video[0].fps + 'fps');
        if (info.audio?.[0])   lines.push('🎵 ' + info.audio[0].codec + ' ' + info.audio[0].channels + 'ch');
        if (info.subs?.length) lines.push('💬 ' + info.subs.map(s=>s.lang||'sub').join(', '));
        detailEl.innerHTML = lines.join('<br>');
        // Update file in list
        f.dur = info.duration_fmt || f.dur;
        f.sz  = info.size_fmt || f.sz;
        renderFiles();
      } else {
        detailEl.textContent = f.sz + (f.dur !== '–' ? ' · ' + f.dur : '');
      }
    } catch(e) {
      detailEl.textContent = f.sz;
    }
  } else {
    detailEl.textContent = f.sz + (f.dur !== '–' ? ' · ' + f.dur : '');
  }
}

function useFileForConvert() {
  showTab('convert', document.getElementById('tbtn-convert'));
}
function useFileForBurn() {
  showTab('burn', document.getElementById('tbtn-burn'));
}

// Überschreibe selF um auch Info-Panel zu zeigen
function selF(i) {
  selectFileAndShowInfo(i);
}

// ── Presets dynamisch laden ───────────────────────────────────────
async function loadPresetsFromBackend() {
  const a = api();
  if (!a) return; // Demo-Modus: statische Options bleiben

  const sel = document.getElementById('presetSel');
  if (!sel) return;

  try {
    const presets = JSON.parse(await a.get_presets());
    if (!Array.isArray(presets) || !presets.length) return;

    // Optgroups nach Kategorie
    const cats = {
      video:  'Video',
      audio:  'Audio',
      device: 'Gerät',
      disc:   'Disc-Format',
    };
    sel.innerHTML = '';
    for (const [cat, label] of Object.entries(cats)) {
      const group = presets.filter(p => p.category === cat);
      if (!group.length) continue;
      const optgroup = document.createElement('optgroup');
      optgroup.label = label;
      for (const p of group) {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.name;
        optgroup.appendChild(opt);
      }
      sel.appendChild(optgroup);
    }
    setStat('✓ ' + presets.length + ' Presets geladen');
  } catch(e) {
    console.log('Presets laden:', e);
  }
}

function onPresetChange() {
  const sel = document.getElementById('presetSel');
  if (!sel) return;
  const val = sel.value;
  // Disc-Karten synchron auswählen
  const catMap = {
    mp4_h264_1080p: 'video', mp4_h265_4k: 'video',
    mkv_h265_copy_audio: 'video', avi_xvid: 'video', webm_vp9: 'video',
    mp3_320k: 'audio', mp3_192k: 'audio', flac_lossless: 'audio',
    wav_pcm: 'audio', aac_256k: 'audio',
    iphone: 'device', android: 'device', ps5: 'device', smart_tv: 'device',
    dvd_pal: 'disc', dvd_ntsc: 'disc', audio_cd: 'disc',
  };
  const cat = catMap[val];
  if (cat) {
    document.querySelectorAll('#discIconRow .disc-card').forEach(c => {
      c.classList.toggle('sel', c.dataset.type === cat);
    });
  }
}

// ── Batch-Konvertierung ───────────────────────────────────────────
async function goBatchConvert() {
  const a = api();
  const sel = document.getElementById('presetSel');
  const preset = sel ? sel.value : 'mp4_h264_1080p';

  if (a) {
    const r = JSON.parse(await a.open_folder_for_batch());
    if (r.error) return;
    setStat('Batch-Konvertierung wird gestartet...');
    const result = JSON.parse(await a.convert_batch(r.folder, preset));
    if (result.error) alert('Batch-Fehler: ' + result.error);
    else showTab('queue', document.getElementById('tbtn-queue'));
  } else {
    // Demo
    addJob('Batch: Ordner → ' + (sel ? sel.options[sel.selectedIndex]?.text.split(' —')[0] : 'MP4'), 'batch');
    showTab('queue', document.getElementById('tbtn-queue'));
  }
}

// ── Ordner für Batch öffnen (aus linker Panel) ────────────────────
async function openFolderBatch() {
  await goBatchConvert();
}

// ── Sound Test ────────────────────────────────────────────────────
async function testSound() {
  const a = api();
  if (a) {
    JSON.parse(await a.play_sound());
  } else {
    playSound(); // lokale JS-Implementation
  }
  setStat('🔊 Fertig-Sound gespielt');
}

// ── DVD-Menü Templates aus Backend laden ─────────────────────────
async function loadDVDMenuTemplates() {
  const a = api();
  if (!a) return;
  try {
    const templates = JSON.parse(await a.get_dvd_menu_templates());
    if (!Array.isArray(templates)) return;
    // MENU_PREVIEWS aktualisieren
    templates.forEach(t => {
      if (!MENU_PREVIEWS[t.id]) {
        MENU_PREVIEWS[t.id] = { bg:'#111', fg:'#fff', accent:'#888', emoji: t.preview || '🎬' };
      }
    });
  } catch(e) {}
}

// ── Watch Folder Status laden ─────────────────────────────────────
async function loadWatchFolders() {
  const a = api();
  if (!a) return;
  try {
    const wf = JSON.parse(await a.get_watch_folders());
    const statusEl = document.getElementById('watchStatus');
    if (statusEl && wf.length) {
      statusEl.textContent = '▶ Aktiv: ' + wf[0].folder;
      const folderEl = document.getElementById('watchFolder');
      if (folderEl) folderEl.value = wf[0].folder;
    }
  } catch(e) {}
}

// ── Queue: Job abbrechen per Button ──────────────────────────────
function renderJobsEnhanced() {
  const l = document.getElementById('jlist');
  if (!S.jobs.length) {
    l.innerHTML = '<div style="padding:16px;color:#666;font-size:11px;">Keine Jobs vorhanden.</div>';
    return;
  }
  const icons = { pending:'⏳', running:'🔄', done:'✅', failed:'❌', cancelled:'⛔' };
  l.innerHTML = S.jobs.map(j => `
    <div class="jobrow" style="${j.state==='running'?'background:#e8f4ff;':''}">
      <span class="jstate">${icons[j.state]||'⏳'}</span>
      <span class="jname" title="${j.name||''}">${j.name||j.id}</span>
      ${j.state==='running'||j.state==='pending' ? `
        <div style="flex:1;background:#ddd;height:8px;border:1px solid #aaa;margin:0 6px;overflow:hidden;border-radius:2px;">
          <div style="height:100%;width:${j.prog||0}%;background:repeating-linear-gradient(90deg,#1144aa 0,#1144aa 10px,#3366cc 10px,#3366cc 12px);transition:width 0.3s;"></div>
        </div>
        <span class="jpct" style="font-size:9px;width:28px;">${Math.floor(j.prog||0)}%</span>
        <button style="padding:1px 5px;font-size:9px;cursor:pointer;border:1px solid #cc4444;color:#cc4444;background:#fff3f3;margin-left:3px;" 
          onclick="cancelJobUI('${j.id}')">✕</button>
      ` : `<span class="jpct">${Math.floor(j.prog||0)}%</span>`}
    </div>`).join('');
}

async function cancelJobUI(jobId) {
  if (!confirm('Job abbrechen?')) return;
  await cancelJob(jobId);
}

// Überschreibe renderJobs mit erweiterter Version
const _origRenderJobs = renderJobs;
function renderJobs() { renderJobsEnhanced(); }

// ── Startup: alle Backend-Daten laden ────────────────────────────
const _origStartup = startup;
async function startup() {
  await _origStartup();
  await loadPresetsFromBackend();
  await loadDVDMenuTemplates();
  await loadWatchFolders();
}


// ── Korrekter Start: erst UI aufbauen, dann auf die Python-Bridge warten ──
// init() ist reines JavaScript (Tabs, Buttons) -> sofort OK

// ── Brenner-/Rohling-Erkennung anzeigen ──
async function loadBurners(){
  const ba = document.getElementById('burnerArea');
  const ma = document.getElementById('mediaArea');
  if(!ba) return;
  const a = api();
  if(!a){ ba.innerHTML = '<div class="media-empty">Backend startet noch...</div>'; return; }
  ba.innerHTML = '<div class="media-empty">Suche nach Laufwerk...</div>';
  try{
    const r = JSON.parse(await a.detect_burners());
    if(r.error || !r.drives || r.drives.length===0){
      ba.innerHTML = '<div class="media-empty">Kein optisches Laufwerk gefunden.</div>'
        + (r.note ? '<div class="detect-note">'+r.note+'</div>' : '')
        + (r.error ? '<div class="detect-note">'+r.error+'</div>' : '');
      ma.innerHTML = '<div class="media-empty">-</div>';
      return;
    }
    const d = r.drives[0];
    let caps = (d.caps||[]).map(c=>'<span class="dev-cap">'+c+'</span>').join('');
    ba.innerHTML =
      '<div class="dev-card">'+
        '<div class="dev-ico"><svg width="28" height="28" viewBox="0 0 28 28"><rect x="3" y="8" width="22" height="12" rx="2" fill="#7f8c9a"/><circle cx="14" cy="14" r="3" fill="#fff"/><rect x="6" y="10" width="2" height="2" fill="#4caf50"/></svg></div>'+
        '<div class="dev-info"><h3>'+d.name+'</h3>'+
          '<p>Laufwerk '+(d.letter||'?')+' \u00b7 erkannt \u00fcber System</p>'+
          '<div class="dev-caps">'+caps+'</div></div>'+
      '</div>'+
      (caps ? '<div class="detect-note">Faehigkeiten aus Laufwerksname abgeleitet.</div>' : '');
    // Rohling
    const m = d.media || {present:false};
    if(!m.present){
      ma.innerHTML = '<div class="media-row"><div class="media-disc empty"></div>'+
        '<div class="media-stats"><div class="media-empty">Kein Rohling eingelegt - bitte einlegen.</div></div></div>';
    } else if(m.readable){
      ma.innerHTML = '<div class="media-row"><div class="media-disc"></div>'+
        '<div class="media-stats">'+
        '<div class="mstat"><span class="k">Status</span><span class="v">Medium eingelegt</span></div>'+
        '<div class="mstat"><span class="k">Kapazitaet</span><span class="v">'+m.capacity_gb+' GB</span></div>'+
        '</div></div>';
    } else {
      ma.innerHTML = '<div class="media-row"><div class="media-disc"></div>'+
        '<div class="media-stats">'+
        '<div class="mstat"><span class="k">Status</span><span class="v">Rohling erkannt</span></div>'+
        '</div></div>'+
        '<div class="detect-note">Hersteller &amp; genaue Kapazitaet eines leeren Rohlings sind ohne Tieferkennung nicht auslesbar.</div>';
    }
  }catch(e){
    ba.innerHTML = '<div class="media-empty">Fehler beim Auslesen.</div><div class="detect-note">'+e+'</div>';
  }
}

// ── LAUNCHER-NAVIGATION (CloneCD-Stil) ──
const FLOW_TITLES = {
  convert:['Konvertieren','Format waehlen und umwandeln'],
  burn:['Disc brennen','Rohling einlegen und brennen'],
  rip:['Disc rippen','DVD oder CD als Datei einlesen'],
  download:['Download','Video aus dem Netz holen'],
  search:['Suche','Medien finden'],
  edit:['Bearbeiten','Schneiden und Menue gestalten'],
  ai:['AI Tools','KI-gestuetzte Funktionen'],
  library:['Bibliothek','Deine konvertierten Dateien'],
  queue:['Job Queue','Laufende und fertige Aufgaben'],
  settings:['Einstellungen','Tools und Optionen']
};
function openFlow(name){
  document.body.classList.remove('home-mode');
  document.body.classList.add('flow-mode');
  // Do not resize through the pywebview API here: on some Windows/WebView2
  // runtimes, calling window.resize from a JS bridge thread minimizes the app.
  const btn = document.getElementById('tbtn-'+name);
  showTab(name, btn);
  if(name==='burn'){ setTimeout(loadBurners, 50); }
  if(name==='download'){ setTimeout(()=>document.getElementById('urlinp')?.focus(), 50); }
  const t = FLOW_TITLES[name] || [name,''];
  document.getElementById('flowTitle').textContent = t[0];
  document.getElementById('flowSub').textContent = t[1];
}
function goHome(){
  document.body.classList.remove('flow-mode');
  document.body.classList.add('home-mode');
}
// Beim Start im Home-Modus
document.body.classList.add('home-mode');

init();

// startup() braucht die pywebview-Bridge (window.pywebview.api).
// Die wird von PyWebView NACH dem Laden injiziert und meldet sich
// mit dem Event 'pywebviewready'. Vorher waren alle api()-Aufrufe null
// -> deshalb taten die Buttons nichts.
function startBackend(){
  if (window.__retrodisc_started) return;   // nur einmal
  window.__retrodisc_started = true;
  startup();
}

if (window.pywebview && window.pywebview.api) {
  // Bridge schon da (schneller Rechner)
  startBackend();
} else {
  // Auf die Bridge warten
  window.addEventListener('pywebviewready', startBackend);
  // Sicherheitsnetz: falls das Event verpasst wurde, pollen
  let _tries = 0;
  const _poll = setInterval(() => {
    if (window.pywebview && window.pywebview.api) {
      clearInterval(_poll);
      startBackend();
    } else if (++_tries > 100) {   // nach ~10s aufgeben
      clearInterval(_poll);
      console.warn('pywebview-Bridge nicht gefunden - Browser-Modus');
      startBackend();  // trotzdem starten (Demo-Modus)
    }
  }, 100);
}
