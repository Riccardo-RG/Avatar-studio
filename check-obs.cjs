const assert=require('node:assert/strict');
const {run,authentication}=require('./obs_bridge.cjs');
let calls=[],existing=false;
class FakeSocket extends EventTarget{
 constructor(url){super();assert.match(url,/^ws:\/\/127.0.0.1:4455$/);queueMicrotask(()=>this.reply({op:0,d:{authentication:{salt:'salt',challenge:'challenge'}}}));}
 reply(data){this.dispatchEvent(new MessageEvent('message',{data:JSON.stringify(data)}));}
 send(raw){const m=JSON.parse(raw);if(m.op===1){assert.equal(m.d.authentication,authentication('password','salt','challenge'));queueMicrotask(()=>this.reply({op:2,d:{negotiatedRpcVersion:1}}));return;}
 const {requestType,requestId,requestData}=m.d;calls.push({requestType,requestData});let data={};
 if(requestType==='GetSceneList')data={scenes:existing?[{sceneName:'Avatar Studio'}]:[]};
 if(requestType==='GetInputList')data={inputs:existing?[{inputName:'Avatar Studio · scena locale'}]:[]};
 if(requestType==='GetSceneItemList')data={sceneItems:[]};
 queueMicrotask(()=>this.reply({op:7,d:{requestType,requestId,requestStatus:{result:true,code:100},responseData:data}}));}
 close(){}
}
(async()=>{global.WebSocket=FakeSocket;const cfg={port:4455,password:'password',scene_url:'http://127.0.0.1:8765/live-scene.html?obs=1'};
 await run({...cfg,action:'setup'});assert(calls.some(c=>c.requestType==='CreateScene'));assert(calls.some(c=>c.requestType==='CreateInput'&&c.requestData.inputSettings.reroute_audio));
 calls=[];existing=true;await run({...cfg,action:'setup'});assert(!calls.some(c=>c.requestType==='CreateScene'));assert(calls.some(c=>c.requestType==='CreateSceneItem'));
 calls=[];await run({...cfg,action:'status'});assert.deepEqual(calls.map(c=>c.requestType),['GetVersion','GetStreamStatus','GetRecordStatus']);
 console.log('OBS WebSocket: autenticazione, creazione scena, riuso sorgente e lettura stato verificati con simulatore; nessun OBS reale contattato.');
})().catch(e=>{console.error(e);process.exit(1);});
