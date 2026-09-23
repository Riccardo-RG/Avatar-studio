const fs=require('fs'),path=require('path'),os=require('os');
const local=path.join(__dirname,'node_modules/playwright'),legacy=path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
module.exports={playwright:process.env.AVATAR_PLAYWRIGHT||(fs.existsSync(local)?local:fs.existsSync(legacy)?legacy:'playwright'),chrome:process.env.AVATAR_CHROME||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'};
