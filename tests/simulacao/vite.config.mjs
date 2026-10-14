// Harness QA: preserva plugins/config original; só adapta host e proxy do preview.
import { defineConfig, mergeConfig } from '../../frontend/node_modules/vite/dist/node/index.js';
import original from '../../frontend/vite.config.ts';
export default mergeConfig(original, defineConfig({
  root: new URL('../../frontend', import.meta.url).pathname,
  server: {host:'0.0.0.0',port:5173,allowedHosts:['.e2b.app','localhost'],proxy:{
    '/api':'http://127.0.0.1:8000',
    '/attachments':'http://127.0.0.1:8000',
    '/ws':{target:'ws://127.0.0.1:8000',ws:true}
  }}
}));
