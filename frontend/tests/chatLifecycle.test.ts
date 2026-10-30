import assert from 'node:assert/strict';
import { it } from 'node:test';
import { createRequire } from 'node:module';
const { createHarness, find, flush } = createRequire(import.meta.url)('./helpers/chatHarness.cjs');

it('clear aborts A and isolates its pending read/finally from new request B', async () => {
  const h=createHarness();
  const chat=h.mount(h.load('hooks/useChat.ts').useChat,'K49');
  const a=chat.value.sendMessage('A');await flush();chat.render();
  const old=h.requests[0];
  chat.value.clearMessages();
  const b=chat.value.sendMessage('B');await flush();await a;chat.render();
  assert.equal(old.init.signal.aborted,true);
  assert.equal(old.cancelled,true);
  assert.equal(old.body.locked,false);
  assert.equal(chat.value.isTyping,true);
  assert.equal(chat.value.messages.length,2);
  assert.equal(chat.value.messages[0].content,'B');
  assert.equal(JSON.parse(h.requests[1].init.body).chat_history.length,0);
  h.advance(1000);chat.render();
  assert.equal(chat.value.isTyping,true);
  h.requests[1].push('token',{text:'answer B'});
  h.requests[1].push('done',{status:'answered',citations_used:[]});
  await b;h.advance(1000);chat.render();
  assert.equal(chat.value.messages.at(-1).content,'answer B');
  assert.equal(chat.value.isTyping,false);
  assert.equal(h.timers.size,0);
});

it('idle timeout covers body reads, resets on data, and cleans reader/timers', async () => {
  const h=createHarness(),chat=h.mount(h.load('hooks/useChat.ts').useChat,'K49');
  const pending=chat.value.sendMessage('question');await flush();
  h.advance(29000);
  h.requests[0].push('token',{text:'partial'});await flush();
  h.advance(29000);chat.render();assert.equal(chat.value.isTyping,true);
  h.advance(1000);await pending;chat.render();
  assert.equal(h.requests[0].init.signal.aborted,true);
  assert.equal(h.requests[0].body.locked,false);
  assert.equal(chat.value.isTyping,false);
  assert.match(chat.value.messages.at(-1).content,/partial.*\n\n/s);
  assert.equal(h.timers.size,0);
});

it('terminal SSE without EOF preserves sources, releases reader and clears timeout', async () => {
  const h=createHarness(),chat=h.mount(h.load('hooks/useChat.ts').useChat,'K49');
  const pending=chat.value.sendMessage('question');await flush();
  const r=h.requests[0];
  r.push('metadata',{run_id:'run',citations_used:[{chunk_id:'source',content:'evidence'}]});
  r.push('token',{text:'answer'});r.push('done',{status:'answered',citations_used:[{chunk_id:'source',content:'evidence'}]});
  await pending;h.advance(1000);chat.render();
  assert.equal(r.body.locked,false);assert.equal(r.cancelled,true);
  assert.equal(chat.value.messages.at(-1).runId,'run');
  assert.equal(chat.value.messages.at(-1).citations[0].chunk_id,'source');
  assert.equal(JSON.parse(h.storage.get('chat_messages')).at(-1).isStreaming,false);
  assert.equal(h.timers.size,0);
});

it('unmount cancels the stream and removes all timers', async () => {
  const h=createHarness(),chat=h.mount(h.load('hooks/useChat.ts').useChat,'K49');
  const pending=chat.value.sendMessage('question');await flush();chat.unmount();await pending;
  assert.equal(h.requests[0].init.signal.aborted,true);
  assert.equal(h.requests[0].body.locked,false);
  assert.equal(h.timers.size,0);
});

for(const mobile of [false,true])for(const conversation of [false,true]) {
  it(`App -> ChatArea -> composer restores draft after tab remount (${mobile?'mobile':'desktop'}, ${conversation?'conversation':'empty'})`,()=>{
    const h=createHarness({mobile});
    if(conversation)h.fakeChat.messages=[{id:'old',role:'user',content:'old'}];
    const app=h.mount(h.load('App.tsx').default);
    const navigate=tab=>{
      find(app.value,n=>n.type===(mobile?'BottomTabBar':'Sidebar')).props.onTabChange(tab);app.render();
    };
    const composer=()=>{
      const areaNode=find(app.value,n=>n.type===h.load('components/ChatArea.tsx').ChatArea);
      const area=h.mount(areaNode.type,areaNode.props);
      let tree=area.value;
      if(!conversation){
        const empty=find(tree,n=>n.type===h.load('components/ChatEmptyState.tsx').ChatEmptyState);
        tree=h.mount(empty.type,empty.props).value;
      }
      const node=find(tree,n=>n.type===h.load('components/ChatInput.tsx').ChatInput);
      if(!conversation)assert.equal(node.props.initialText,'');
      return h.mount(node.type,node.props);
    };
    navigate('chat');const first=composer();
    find(first.value,n=>n.type==='textarea').props.onChange({target:{value:'unsent draft'}});first.render();first.unmount();
    navigate('tools');navigate('chat');const second=composer();
    assert.equal(find(second.value,n=>n.type==='textarea').props.value,'unsent draft');
    find(second.value,n=>n.type==='form').props.onSubmit({preventDefault(){}});
    assert.equal(h.storage.has('hcmue-chat-draft'),false);
  });
}

it('feedback HTTP failure preserves comment and permits successful retry',async()=>{
  const h=createHarness();let attempts=0;
  h.context.fetch=async()=>({ok:++attempts>1,status:422});
  const view=h.mount(h.load('components/ChatMessage.tsx').ChatMessage,{message:{id:'m',role:'bot',content:'answer',timestamp:'12:00',runId:'run'}});
  find(view.value,n=>n.props?.['aria-label']==='Chưa chính xác').props.onClick();view.render();
  find(view.value,n=>n.type==='textarea').props.onChange({target:{value:'keep this comment'}});view.render();
  const submit=()=>find(view.value,n=>n.props?.className==='btn-primary').props.onClick();
  await submit();view.render();
  assert.equal(find(view.value,n=>n.type==='textarea').props.value,'keep this comment');
  assert.equal(h.notices.at(-1)[1],'error');
  assert.equal(find(view.value,n=>n.props?.['aria-label']==='Chưa chính xác').props.disabled,false);
  await submit();view.render();
  assert.equal(find(view.value,n=>n.type==='textarea'),undefined);
  assert.equal(h.notices.at(-1)[1],'success');
  assert.equal(find(view.value,n=>n.props?.['aria-label']==='Chưa chính xác').props.disabled,true);
});
