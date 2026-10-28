// Импортируем собранный фреймворк
import './cubism-web-sdk/Framework/dist/live2dcubismframework.js';

const canvas = document.getElementById('live2dCanvas');
canvas.width = window.innerWidth;
canvas.height = window.innerHeight;

// Ждём загрузки модуля
console.log('✅ Модули загружены, Framework готов');

// Пока просто фон
const gl = canvas.getContext('webgl');
gl.clearColor(0.16, 0.16, 0.16, 1.0);
gl.clear(gl.COLOR_BUFFER_BIT);
console.log('✅ WebGL canvas готов');