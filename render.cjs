const fs = require('fs');
const path = require('path');
const {spawn} = require('child_process');
const {once} = require('events');
const {chromium} = require(process.env.AVATAR_PLAYWRIGHT || 'playwright');
const [base, id, folder] = process.argv.slice(2);
let browser, encoder, closing = false;
async function cleanup() {
  if (closing) return;
  closing = true;
  if (encoder && encoder.exitCode === null) encoder.kill('SIGTERM');
  if (browser) await browser.close().catch(() => {});
}
process.on('SIGTERM', async () => {await cleanup(); process.exit(1);});
const watchdog = setTimeout(async () => {console.error('Esportazione oltre il limite di 15 minuti.'); await cleanup(); process.exit(1);}, 900000);
(async () => {
  const project = JSON.parse(fs.readFileSync(path.join(folder, 'project.json'), 'utf8'));
  const resolution=project.settings.resolution, format=project.settings.format||'portrait';
  const width = format==='landscape'?Math.round(resolution*16/9):resolution, height = format==='portrait'?Math.round(resolution*16/9):resolution, fps = 24;
  browser = await chromium.launch({executablePath: process.env.AVATAR_CHROME, headless: true,
    args: ['--autoplay-policy=no-user-gesture-required', '--enable-unsafe-swiftshader']});
  const page = await browser.newPage({viewport: {width, height}});
  page.on('pageerror', e => console.error(e.message));
  await page.goto(`${base}/render.html?job=${id}`);
  await page.waitForFunction(() => window.renderReady === true, {timeout: 30000});
  const cover = await page.evaluate(() => window.renderCover());
  fs.writeFileSync(path.join(folder, 'cover.png'), Buffer.from(cover.split(',')[1], 'base64'));
  const music=project.music&&process.env.AVATAR_MUSIC;
  const audioArgs=music?['-stream_loop','-1','-i',process.env.AVATAR_MUSIC,'-filter_complex','[2:a]volume=0.12[bed];[1:a][bed]amix=inputs=2:duration=first:normalize=0[mix]','-map','0:v:0','-map','[mix]']:['-map','0:v:0','-map','1:a:0'];
  encoder = spawn(process.env.AVATAR_FFMPEG, ['-hide_banner', '-loglevel', 'error', '-y',
    '-f', 'image2pipe', '-framerate', String(fps), '-vcodec', 'png', '-i', 'pipe:0',
    '-i', path.join(folder, 'voice.wav'), ...audioArgs,
    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21', '-pix_fmt', 'yuv420p',
    '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', '-shortest', path.join(folder, 'video.mp4')],
    {stdio: ['pipe', 'ignore', 'pipe']});
  let encoderError = '';
  encoder.stderr.on('data', d => {encoderError += d.toString();});
  const finished = new Promise((resolve, reject) => {
    encoder.on('error', reject);
    encoder.on('close', code => code === 0 ? resolve() : reject(new Error(encoderError || `FFmpeg ${code}`)));
  });
  // Keep rejections observed while producing frames.
  finished.catch(() => {});
  encoder.stdin.on('error', () => {});
  const frames = Math.ceil(project.duration * fps);
  for (let frame = 0; frame < frames; frame++) {
    const png = await page.evaluate(t => window.renderFrame(t), frame / fps);
    const bytes = Buffer.from(png.split(',')[1], 'base64');
    if (frame === Math.min(48, frames - 1)) fs.writeFileSync(path.join(folder, 'poster.png'), bytes);
    if (!encoder.stdin.write(bytes)) await once(encoder.stdin, 'drain');
    if (frame % fps === 0) console.log(`PROGRESS ${frame / frames}`);
  }
  encoder.stdin.end();
  await finished;
  console.log('PROGRESS 1');
})().then(async () => {clearTimeout(watchdog); await cleanup();})
  .catch(async e => {console.error(e.stack); clearTimeout(watchdog); await cleanup(); process.exit(1);});
