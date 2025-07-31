import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

// FIXED: Apply saved theme color on initial app load
const savedColor = localStorage.getItem('themeColor')
if (savedColor) {
  const applyThemeColor = (color) => {
    const root = document.documentElement
    
    // Convert hex to HSL for different shades
    const hex = color.replace('#', '')
    const r = parseInt(hex.substr(0, 2), 16)
    const g = parseInt(hex.substr(2, 2), 16)
    const b = parseInt(hex.substr(4, 2), 16)
    
    // Convert RGB to HSL
    const rNorm = r / 255
    const gNorm = g / 255
    const bNorm = b / 255
    
    const max = Math.max(rNorm, gNorm, bNorm)
    const min = Math.min(rNorm, gNorm, bNorm)
    let h, s, l = (max + min) / 2
    
    if (max === min) {
      h = s = 0
    } else {
      const d = max - min
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
      switch (max) {
        case rNorm: h = (gNorm - bNorm) / d + (gNorm < bNorm ? 6 : 0); break
        case gNorm: h = (bNorm - rNorm) / d + 2; break
        case bNorm: h = (rNorm - gNorm) / d + 4; break
      }
      h /= 6
    }
    
    h = Math.round(h * 360)
    s = Math.round(s * 100)
    l = Math.round(l * 100)
    
    // Generate color palette
    root.style.setProperty('--primary-50', `hsl(${h}, ${s}%, 97%)`)
    root.style.setProperty('--primary-100', `hsl(${h}, ${s}%, 93%)`)
    root.style.setProperty('--primary-200', `hsl(${h}, ${s}%, 86%)`)
    root.style.setProperty('--primary-300', `hsl(${h}, ${s}%, 77%)`)
    root.style.setProperty('--primary-400', `hsl(${h}, ${s}%, 65%)`)
    root.style.setProperty('--primary-500', `hsl(${h}, ${s}%, ${l}%)`)
    root.style.setProperty('--primary-600', `hsl(${h}, ${s}%, ${Math.max(l - 10, 20)}%)`)
    root.style.setProperty('--primary-700', `hsl(${h}, ${s}%, ${Math.max(l - 20, 15)}%)`)
    root.style.setProperty('--primary-800', `hsl(${h}, ${s}%, ${Math.max(l - 30, 10)}%)`)
    root.style.setProperty('--primary-900', `hsl(${h}, ${s}%, ${Math.max(l - 40, 5)}%)`)
  }
  
  applyThemeColor(savedColor)
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)