// Run the actual page callbacks and calculation utilities with deterministic hooks.
// Layout/DOM interactions are verified separately in the browser.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const root = path.resolve(__dirname, '../../..');
const ts = require('typescript');
function session(profile) {
  const state = []; let cursor = 0; const cache = new Map();
  const react = {
    useState(init) { const i = cursor++; if (!(i in state)) state[i] = typeof init === 'function' ? init() : init;
      return [state[i], v => state[i] = typeof v === 'function' ? v(state[i]) : v]; },
    useMemo: f => f(), useRef: v => ({current:v}), useEffect() {}, useId: () => 'test',
  };
  const jsx = (type, props) => ({type, props:props || {}});
  function load(file) {
    if (cache.has(file)) return cache.get(file);
    const source = fs.readFileSync(file, 'utf8');
    const module = {exports:{}}; cache.set(file, module.exports);
    const req = name => {
      if (name === 'react') return react;
      if (name === 'react/jsx-runtime') return {jsx, jsxs:jsx, Fragment:'fragment'};
      if (name === 'lucide-react') return new Proxy({}, {get:(_, k) => k});
      if (name.includes('useStudentProfile')) return {useStudentProfile:() => ({profile, update: p => Object.assign(profile,p), clear:() => {}})};
      if (name.includes('useAnimatedNumber')) return {useAnimatedNumber:n => n};
      const target = path.resolve(path.dirname(file), name);
      if (target.includes(path.join('src','utils')) || target.includes(path.join('src','data'))) return load(target + '.ts');
      return new Proxy({}, {get:(_,k)=>k});
    };
    const js = ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.CommonJS, jsx:ts.JsxEmit.ReactJSX, target:ts.ScriptTarget.ES2022}}).outputText;
    vm.runInNewContext('(function(require,module,exports){'+js+'\n})', {window:{confirm:()=>true}, console, setTimeout})(req,module,module.exports);
    cache.set(file,module.exports); return module.exports;
  }
  return {render(page, props={}) {cursor=0; return load(path.join(root,`frontend/src/components/pages/${page}.tsx`))[page](props);}, state};
}
function nodes(n) { if (!n || typeof n !== 'object') return []; if(Array.isArray(n)) return n.flatMap(nodes); return [n,...nodes(n.props?.children)]; }
function text(n) { if(n == null || typeof n === 'boolean') return ''; if(Array.isArray(n)) return n.map(text).join(''); if(typeof n !== 'object') return String(n); return text(n.props?.children); }
function find(tree, predicate) { const n=nodes(tree).find(predicate); if(!n) throw Error('Missing node'); return n; }

module.exports = {session, nodes, text, find};
