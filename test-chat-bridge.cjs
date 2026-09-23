const assert=require('node:assert/strict');const {twitchEvent,youtubeEvents,reconnectURL}=require('./chat_bridge.cjs');
const fixture={metadata:{subscription_type:'channel.chat.message',message_id:'event1'},payload:{event:{chatter_user_name:'Ada',chatter_user_id:'42',message:{text:'Ciao!'},message_id:'message1'}}};
assert.deepEqual(twitchEvent(fixture),{author:'Ada',text:'Ciao!',event_id:'message1',user_id:'42'});
assert.equal(twitchEvent({metadata:{subscription_type:'other'}}),null);
assert.deepEqual(youtubeEvents({items:[{id:'y1',snippet:{type:'textMessageEvent',textMessageDetails:{messageText:'Ciao'}},authorDetails:{displayName:'Luca',channelId:'123'}},{snippet:{type:'messageDeletedEvent'}}]}),[{author:'Luca',text:'Ciao',event_id:'y1',user_id:'123'}]);
assert.equal(reconnectURL('wss://eventsub.wss.twitch.tv/ws?session=abc'),'wss://eventsub.wss.twitch.tv/ws?session=abc');
for(const url of ['ws://eventsub.wss.twitch.tv/','wss://evil.test/ws','wss://eventsub.wss.twitch.tv.evil.test/ws','wss://user:pass@eventsub.wss.twitch.tv/'])assert.throws(()=>reconnectURL(url));
console.log('Chat parsers and reconnect origin checks passed.');
