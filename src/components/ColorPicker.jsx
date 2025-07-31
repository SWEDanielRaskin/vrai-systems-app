import React, { useState, useRef, useEffect, useCallback } from 'react';
import { X } from 'lucide-react';

const ColorPicker = ({ color, onChange, onClose }) => {
  const [hue, setHue] = useState(0);
  const [saturation, setSaturation] = useState(100);
  const [lightness, setLightness] = useState(50);
  const [hexValue, setHexValue] = useState(color);
  const [isDragging, setIsDragging] = useState(false);

  const canvasRef = useRef(null);
  const hueRef = useRef(null);
  const isInitializedRef = useRef(false);

  // Debounced onChange to prevent rapid firing
  const debouncedOnChange = useCallback(
    debounce((newColor) => {
      onChange(newColor);
    }, 50),
    [onChange]
  );

  useEffect(() => {
    if (!isInitializedRef.current) {
      // Convert initial hex color to HSL only once
      const hex = color.replace('#', '');
      const r = parseInt(hex.substr(0, 2), 16) / 255;
      const g = parseInt(hex.substr(2, 2), 16) / 255;
      const b = parseInt(hex.substr(4, 2), 16) / 255;

      const max = Math.max(r, g, b);
      const min = Math.min(r, g, b);
      let h,
        s,
        l = (max + min) / 2;

      if (max === min) {
        h = s = 0;
      } else {
        const d = max - min;
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        switch (max) {
          case r:
            h = (g - b) / d + (g < b ? 6 : 0);
            break;
          case g:
            h = (b - r) / d + 2;
            break;
          case b:
            h = (r - g) / d + 4;
            break;
        }
        h /= 6;
      }

      setHue(Math.round(h * 360));
      setSaturation(Math.round(s * 100));
      setLightness(Math.round(l * 100));
      isInitializedRef.current = true;
    }
  }, [color]);

  useEffect(() => {
    if (isInitializedRef.current) {
      drawColorPicker();
    }
  }, [hue]);

  useEffect(() => {
    if (isInitializedRef.current) {
      const newHex = hslToHex(hue, saturation, lightness);
      setHexValue(newHex);
      debouncedOnChange(newHex);
    }
  }, [hue, saturation, lightness, debouncedOnChange]);

  const hslToHex = (h, s, l) => {
    l /= 100;
    const a = (s * Math.min(l, 1 - l)) / 100;
    const f = (n) => {
      const k = (n + h / 30) % 12;
      const color = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
      return Math.round(255 * color)
        .toString(16)
        .padStart(2, '0');
    };
    return `#${f(0)}${f(8)}${f(4)}`;
  };

  const drawColorPicker = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;

    // Clear canvas first
    ctx.clearRect(0, 0, width, height);

    // Create saturation-lightness gradient more efficiently
    const imageData = ctx.createImageData(width, height);
    const data = imageData.data;

    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const s = (x / width) * 100;
        const l = 100 - (y / height) * 100;

        const rgb = hslToRgb(hue, s, l);
        const index = (y * width + x) * 4;

        data[index] = rgb.r; // Red
        data[index + 1] = rgb.g; // Green
        data[index + 2] = rgb.b; // Blue
        data[index + 3] = 255; // Alpha
      }
    }

    ctx.putImageData(imageData, 0, 0);
  };

  const hslToRgb = (h, s, l) => {
    h /= 360;
    s /= 100;
    l /= 100;

    const c = (1 - Math.abs(2 * l - 1)) * s;
    const x = c * (1 - Math.abs(((h * 6) % 2) - 1));
    const m = l - c / 2;

    let r, g, b;

    if (h < 1 / 6) {
      r = c;
      g = x;
      b = 0;
    } else if (h < 2 / 6) {
      r = x;
      g = c;
      b = 0;
    } else if (h < 3 / 6) {
      r = 0;
      g = c;
      b = x;
    } else if (h < 4 / 6) {
      r = 0;
      g = x;
      b = c;
    } else if (h < 5 / 6) {
      r = x;
      g = 0;
      b = c;
    } else {
      r = c;
      g = 0;
      b = x;
    }

    return {
      r: Math.round((r + m) * 255),
      g: Math.round((g + m) * 255),
      b: Math.round((b + m) * 255),
    };
  };

  const handleCanvasMouseDown = (e) => {
    setIsDragging(true);
    handleCanvasInteraction(e);
  };

  const handleCanvasMouseMove = (e) => {
    if (isDragging) {
      handleCanvasInteraction(e);
    }
  };

  const handleCanvasMouseUp = () => {
    setIsDragging(false);
  };

  const handleCanvasInteraction = (e) => {
    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const x = Math.max(0, Math.min(e.clientX - rect.left, canvas.width));
    const y = Math.max(0, Math.min(e.clientY - rect.top, canvas.height));

    const newSaturation = (x / canvas.width) * 100;
    const newLightness = 100 - (y / canvas.height) * 100;

    setSaturation(Math.round(newSaturation));
    setLightness(Math.round(newLightness));
  };

  const handleHueChange = (e) => {
    const newHue = parseInt(e.target.value);
    setHue(newHue);
  };

  const handleHexChange = (e) => {
    const hex = e.target.value;
    setHexValue(hex);

    if (/^#[0-9A-F]{6}$/i.test(hex)) {
      debouncedOnChange(hex);

      // Convert hex back to HSL
      const r = parseInt(hex.substr(1, 2), 16) / 255;
      const g = parseInt(hex.substr(3, 2), 16) / 255;
      const b = parseInt(hex.substr(5, 2), 16) / 255;

      const max = Math.max(r, g, b);
      const min = Math.min(r, g, b);
      let h,
        s,
        l = (max + min) / 2;

      if (max === min) {
        h = s = 0;
      } else {
        const d = max - min;
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
        switch (max) {
          case r:
            h = (g - b) / d + (g < b ? 6 : 0);
            break;
          case g:
            h = (b - r) / d + 2;
            break;
          case b:
            h = (r - g) / d + 4;
            break;
        }
        h /= 6;
      }

      setHue(Math.round(h * 360));
      setSaturation(Math.round(s * 100));
      setLightness(Math.round(l * 100));
    }
  };

  // Add mouse event listeners for dragging
  useEffect(() => {
    const handleMouseMove = (e) => handleCanvasMouseMove(e);
    const handleMouseUp = () => handleCanvasMouseUp();

    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging]);

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-4 w-80">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">Color Picker</h3>
        <button
          onClick={onClose}
          className="p-1 hover:bg-gray-100 rounded transition-colors"
        >
          <X className="h-4 w-4 text-gray-600" />
        </button>
      </div>

      {/* Main Color Area */}
      <div className="mb-4 relative">
        <canvas
          ref={canvasRef}
          width={280}
          height={200}
          className="border border-gray-300 rounded cursor-crosshair"
          onMouseDown={handleCanvasMouseDown}
        />
        {/* Saturation/Lightness Indicator */}
        <div
          className="absolute w-3 h-3 border-2 border-white rounded-full shadow-md pointer-events-none"
          style={{
            left: `${(saturation / 100) * 280 - 6}px`,
            top: `${((100 - lightness) / 100) * 200 - 6}px`,
          }}
        />
      </div>

      {/* Hue Slider */}
      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Hue
        </label>
        <input
          ref={hueRef}
          type="range"
          min="0"
          max="360"
          value={hue}
          onChange={handleHueChange}
          className="w-full h-6 rounded-lg appearance-none cursor-pointer"
          style={{
            background:
              'linear-gradient(to right, #ff0000 0%, #ffff00 17%, #00ff00 33%, #00ffff 50%, #0000ff 67%, #ff00ff 83%, #ff0000 100%)',
          }}
        />
      </div>

      {/* Color Values */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            H:
          </label>
          <input
            type="number"
            min="0"
            max="360"
            value={hue}
            onChange={(e) =>
              setHue(Math.max(0, Math.min(360, parseInt(e.target.value) || 0)))
            }
            className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            S:
          </label>
          <input
            type="number"
            min="0"
            max="100"
            value={saturation}
            onChange={(e) =>
              setSaturation(
                Math.max(0, Math.min(100, parseInt(e.target.value) || 0))
              )
            }
            className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            L:
          </label>
          <input
            type="number"
            min="0"
            max="100"
            value={lightness}
            onChange={(e) =>
              setLightness(
                Math.max(0, Math.min(100, parseInt(e.target.value) || 0))
              )
            }
            className="w-full px-2 py-1 border border-gray-300 rounded text-sm"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            HEX:
          </label>
          <input
            type="text"
            value={hexValue}
            onChange={handleHexChange}
            className="w-full px-2 py-1 border border-gray-300 rounded text-sm font-mono"
            placeholder="#000000"
          />
        </div>
      </div>

      {/* Color Preview */}
      <div className="flex items-center space-x-3">
        <div
          className="w-12 h-12 rounded-lg border border-gray-300 shadow-sm"
          style={{ backgroundColor: hexValue }}
        />
        <div className="flex-1">
          <p className="text-sm font-medium text-gray-900">Preview</p>
          <p className="text-xs text-gray-600 font-mono">
            {hexValue.toUpperCase()}
          </p>
        </div>
      </div>
    </div>
  );
};

// Debounce utility function
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

export default ColorPicker;
