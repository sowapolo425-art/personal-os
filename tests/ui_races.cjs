// Executes the shipped scripts with a minimal DOM; full browser acceptance is separate.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const assert=require('node:assert/strict');
class Element{
  constructor(tag='div'){this.tagName=tag;this.children=[];this.dataset={};this.value='';this.files=[];this.hidden=true;this.checked=false;this.open=false;this.listeners={};this.classList={toggle(){}};this._text='';}
  get textContent(){return this._text+this.children.map(c=>c.textContent||'').join('');}
  set textContent(value){this._text=String(value);this.children=[];}
  append(...children){this.children.push(...children);}
  prepend(...children){this.children.unshift(...children);}
  replaceChildren(...children){this._text='';this.children=[...children];}
  replaceWith(){}
  insertBefore(child){this.children.push(child);}
  setAttribute(){}
  addEventListener(name,fn){this.listeners[name]=fn;}
  cloneNode(){const clone=new Element(this.tagName);clone.value=this.value;clone.textContent=this._text;return clone;}
  querySelector(){return new Element();}
  showModal(){this.open=true;}
  close(){this.open=false;}
  click(){return this.onclick?.();}
  reset(){}
}
const elements=new Map();
const get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
const empty={total:0,pending:0,confirmed:0,kinds:{},created_dates:[],records:[],matching:0,proposals:[],graph:{nodes:[],edges:[],total_nodes:0}};
const context=vm.createContext({
  document:{hidden:false,getElementById:get,createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag),querySelector:()=>new Element(),querySelectorAll:()=>[]},
  fetch:async()=>({ok:true,json:async()=>empty}),console,URL,URLSearchParams,TextDecoder,TextEncoder,
  setTimeout,clearTimeout,setInterval:()=>0,navigator:{clipboard:{writeText:async()=>{}}},confirm:()=>true,
});
for(const file of ['app.js','features.js','memory.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/personal_os/static',file),'utf8'),context,{filename:file});
async function main(){
  await new Promise(setImmediate);
  const result=await vm.runInContext(`(async()=>{
    const originalApi=api;
    const empty=${JSON.stringify(empty)};
    const record=id=>({id,title:id,kind:'record',status:'self_report',revision:1,content:'body-'+id,source:'fictional',tags:[],created_at:'2026-10-10T00:00:00Z',updated_at:'2026-10-10T00:00:00Z'});
    let release;
    api=async route=>{if(route.startsWith('/api/record')){await new Promise(r=>release=r);return record('secret');}if(route.startsWith('/api/history'))return [];return empty;};
    $('restricted').checked=true;
    const pending=openRecord('secret');
    $('restricted').checked=false;$('restricted').onchange();
    release();await pending;
    const privacy=!$('record-dialog').open&&!$('record-content').textContent.includes('secret');
    closeRecord();
    api=async route=>{if(route.startsWith('/api/record')){const id=new URLSearchParams(route.split('?')[1]).get('id');if(id==='A')await new Promise(r=>release=r);return record(id);}if(route.startsWith('/api/history'))return [];return empty;};
    const first=openRecord('A');const second=openRecord('B');await second;release();await first;
    const latestRecord=$('record-title').textContent==='B';closeRecord();
    api=async(route,body)=>{if(route==='/api/import-preview'){if(body.filename==='A.txt')await new Promise(r=>release=r);return {preview_id:body.filename,items:[{key:body.filename,title:body.filename,content:body.text,duplicate:false}]};}return empty;};
    const file=name=>({name,size:1,arrayBuffer:async()=>new TextEncoder().encode(name).buffer});
    $('import-file').files=[file('A.txt')];const oldImport=$('import-file').onchange();
    await new Promise(r=>setTimeout(r,0));
    $('import-file').files=[file('B.txt')];await $('import-file').onchange();release();await oldImport;
    const latestImport=importPreview.preview_id==='B.txt';
    api=originalApi;
    const a={...record('A'),excerpt:'a'},b={...record('B'),excerpt:'b'};
    analysisSelected.add('A');state.view='analysis';renderExtras({...empty,records:[a,b],matching:2});
    state.view='records';renderExtras({...empty,records:[b],matching:1});
    const stableSelection=analysisSelected.has('A');
    analysisText='old preview';$('analysis-result').hidden=false;
    state.view='analysis';renderAnalysisSelection({...empty,records:[b],matching:1});
    const invalidatedPreview=analysisText===null&&$('analysis-result').hidden;
    return {privacy,latestRecord,latestImport,stableSelection,invalidatedPreview};
  })()`,context);
  for(const [name,passed] of Object.entries(result))assert.equal(passed,true,name);
  console.log(JSON.stringify(result));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
