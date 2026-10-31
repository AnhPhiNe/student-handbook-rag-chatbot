// Execute production TS/TSX with deterministic hooks, timers and HTTP, without
// installing a DOM renderer. JSX nodes retain real component identities/props.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const src = path.resolve(__dirname, '../../src');

exports.createHarness = function ({ mobile = false } = {}) {
  const storage = new Map(), timers = new Map(), requests = [], notices = [];
  let current, serial = 0, now = 0;
  const same = (a, b) => a && b && a.length === b.length && a.every((v, i) => Object.is(v, b[i]));
  const react = {
    useState(init) {
      const scope = current, i = scope.cursor++;
      if (!(i in scope.slots)) scope.slots[i] = typeof init === 'function' ? init() : init;
      return [scope.slots[i], v => {
        const next = typeof v === 'function' ? v(scope.slots[i]) : v;
        if (!Object.is(next, scope.slots[i])) { scope.slots[i] = next; scope.dirty = true; }
      }];
    },
    useRef(init) { const i = current.cursor++; return current.slots[i] ||= { current: init }; },
    useEffect(fn, deps) {
      const scope = current, i = scope.cursor++, old = scope.slots[i];
      if (!old || !same(old.deps, deps)) {
        scope.pending.push(() => { old?.cleanup?.(); scope.slots[i] = { deps, cleanup: fn() }; });
      }
    },
    useCallback(fn, deps) {
      const i = current.cursor++, old = current.slots[i];
      if (!old || !same(old.deps, deps)) current.slots[i] = { deps, fn };
      return current.slots[i].fn;
    },
    memo: fn => fn,
    lazy: () => 'LazyPage',
    Suspense: 'Suspense',
  };
  const storageApi = {getItem:k=>storage.get(k) ?? null, setItem:(k,v)=>storage.set(k,v), removeItem:k=>storage.delete(k)};
  const setTimer = (fn, ms, repeat) => { const id=++serial; timers.set(id,{fn,ms,at:now+ms,repeat}); return id; };
  const context = vm.createContext({
    console: {error(){}, warn(){}}, AbortController, DOMException, TextDecoder,
    sessionStorage: storageApi,
    setTimeout:(fn,ms)=>setTimer(fn,ms,false), clearTimeout:id=>timers.delete(id),
    setInterval:(fn,ms)=>setTimer(fn,ms,true), clearInterval:id=>timers.delete(id),
    window:{addEventListener(){},removeEventListener(){},localStorage:storageApi,confirm:()=>true},
    document:{documentElement:{setAttribute(){}},activeElement:null},
    fetch: async (url, init) => {
      let controller;
      const request = {url,init,cancelled:false};
      request.body = new ReadableStream({start(c){controller=c;},cancel(){request.cancelled=true;}});
      request.push = (event,data) => controller.enqueue(new TextEncoder().encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
      request.fail = error => controller.error(error);
      requests.push(request);
      return {ok:true,body:request.body};
    },
  });
  Object.assign(context.window, {setTimeout:context.setTimeout,clearTimeout:context.clearTimeout});
  const cache = new Map();
  const fakeChat = {messages:[],isTyping:false,sendMessage(){},clearMessages(){},retryLastMessage(){},regenerateLastMessage(){}};
  const componentStub = new Proxy({}, {get:(_,key)=>String(key)});
  function load(relative) {
    const file = path.resolve(src, relative);
    if(cache.has(file))return cache.get(file).exports;
    const module={exports:{}}; cache.set(file,module);
    const js=ts.transpileModule(fs.readFileSync(file,'utf8').replaceAll('import.meta.env.VITE_API_BASE_URL','undefined'),{
      fileName:file,compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX},
    }).outputText;
    const requireMock = name => {
      if(name==='react')return {...react,default:react};
      if(name==='react/jsx-runtime')return {jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})};
      if(name==='react-dom')return {createPortal:node=>node};
      if(name==='lucide-react')return componentStub;
      if(name.endsWith('.css'))return {};
      if(name.includes('clientIdentity'))return {getApiClientHeaders:()=>({'Content-Type':'application/json'})};
      if(name.endsWith('/Toast'))return {useToast:()=>({show:(...args)=>notices.push(args)})};
      if(name.includes('useAccessibleDialog'))return {useAccessibleDialog:()=>({current:null})};
      if(name.includes('useMediaQuery'))return {useMediaQuery:q=>q.includes('min-width')?!mobile:mobile};
      if(name.includes('useLocalStorage'))return {useLocalStorage:(key,init)=>react.useState(key==='hcmue-cohort'?'K49':init)};
      if(name.includes('features'))return {IS_CHAT_MAINTENANCE:false,SHOW_EXPERIENCE_PAGE:false};
      if(name.includes('cohortNotice'))return {shouldNotifyCohortChange:()=>false,KEPT_DATA_NOTES:{}};
      if(name.includes('recentTool'))return {readRecentTool:()=>null};
      if(name.includes('welcomeEntrance'))return {WELCOME_ENTRANCE_STORAGE_KEY:'hcmue-welcome-entrance-seen',shouldShowWelcomeEntrance:()=>false};
      if(name.includes('gradeScale'))return {normalizeFrontendCohort:x=>x};
      if(name.endsWith('/useChat') && file.endsWith('App.tsx'))return {useChat:()=>fakeChat};
      const target=path.resolve(path.dirname(file),name);
      if(['ChatArea','ChatInput','ChatEmptyState','ChatMessage','streamCompletion','queryLength'].includes(path.basename(target))) {
        return load(path.relative(src,target)+(target.includes('components')?'.tsx':'.ts'));
      }
      return componentStub;
    };
    vm.runInContext(`(function(require,module,exports){${js}\n})`,context)(requireMock,module,module.exports);
    return module.exports;
  }
  const mount = (fn, props) => {
    const scope={slots:[],pending:[],cursor:0,dirty:false,value:null};
    scope.render=()=>{
      let renders=0;
      do {
        if(++renders>20)throw Error('Unstable render');
        scope.cursor=0;scope.dirty=false;current=scope;
        scope.value=fn(props); current=null;
        for(const effect of scope.pending.splice(0))effect();
      } while(scope.dirty);
      return scope.value;
    };
    scope.unmount=()=>{for(const slot of scope.slots)slot?.cleanup?.();};
    scope.render();return scope;
  };
  const advance = ms => {
    const end=now+ms;
    while(true){
      const next=[...timers.entries()].filter(([,t])=>t.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];
      if(!next)break;
      const [id,t]=next;now=t.at;
      if(t.repeat)t.at+=t.ms;else timers.delete(id);
      t.fn();
    }
    now=end;
  };
  return {load,mount,storage,requests,notices,fakeChat,context,timers,advance};
};
exports.find = function find(node, predicate) {
  if(!node || typeof node!=='object')return undefined;
  if(Array.isArray(node))return node.map(x=>find(x,predicate)).find(Boolean);
  return predicate(node)?node:find(node.props?.children,predicate);
};
exports.flush = async () => {for(let i=0;i<20;i++)await Promise.resolve();};
