// Configuration for backend URLs
const config = {
  development: {
    backendUrl: 'http://localhost:5000',
    websocketUrl: 'ws://localhost:8080'
  },
  production: {
    backendUrl: import.meta.env.VITE_BACKEND_URL || 'https://your-railway-app.railway.app',
    websocketUrl: import.meta.env.VITE_WEBSOCKET_URL || 'wss://your-railway-app.railway.app'
  }
};

const environment = import.meta.env.MODE || 'development';
export const backendUrl = config[environment].backendUrl;
export const websocketUrl = config[environment].websocketUrl;

export default config[environment]; 