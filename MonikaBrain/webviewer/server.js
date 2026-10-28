import { WebSocketServer } from 'ws';
import { initModel, model } from './main.js'; // экспортируем модель

const wss = new WebSocketServer({ port: 8080 });

wss.on('connection', ws => {
    console.log('Python подключился к WebSocket');

    ws.on('message', message => {
        try {
            const data = JSON.parse(message);
            handleCommand(data);
        } catch (e) {
            console.error('Неверный JSON', e);
        }
    });
});

function handleCommand(cmd) {
    if (!model) return;

    switch(cmd.action) {
        case 'setEmotion':
            // Например, paramName в model3.json — "happy"
            model.setParameter(cmd.param, cmd.value); 
            break;
        case 'rotateHead':
            model.setParameter('ParamAngleX', cmd.x); // наклон головы по X
            model.setParameter('ParamAngleY', cmd.y); // наклон головы по Y
            break;
        case 'blink':
            model.setParameter('ParamEyeLOpen', cmd.value);
            model.setParameter('ParamEyeROpen', cmd.value);
            break;
    }
}