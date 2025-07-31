import React from 'react'
import { Lock, Unlock } from 'lucide-react'

const AppleToggle = ({ value, onChange, options, isLocked, onLockToggle }) => {
  const getPositionClass = () => {
    switch (value) {
      case 'business':
        return 'translate-x-0'
      case 'actual':
        return 'translate-x-full'
      case 'after_hours':
        return 'translate-x-[200%]'
      default:
        return 'translate-x-full'
    }
  }

  const handleToggleClick = (optionValue) => {
    if (!isLocked) {
      onChange(optionValue)
    }
  }

  return (
    <div className="flex items-center space-x-3">
      {/* Lock Button */}
      <button
        onClick={onLockToggle}
        className={`p-2 rounded-lg transition-all duration-200 ${
          isLocked 
            ? 'bg-gray-100 hover:bg-gray-200 text-gray-600' 
            : 'bg-orange-100 hover:bg-orange-200 text-orange-600'
        }`}
        title={isLocked ? 'Click to unlock toggle' : 'Click to lock toggle'}
      >
        {isLocked ? (
          <Lock className="h-4 w-4" />
        ) : (
          <Unlock className="h-4 w-4" />
        )}
      </button>

      {/* Toggle Container */}
      <div className={`relative rounded-full p-1 w-64 h-10 shadow-inner transition-all duration-200 ${
        isLocked 
          ? 'bg-gray-200 opacity-75' 
          : 'bg-gray-200'
      }`}>
        {/* Sliding Background */}
        <div 
          className={`absolute top-1 left-1 w-[calc(33.333%-0.25rem)] h-8 bg-white rounded-full shadow-lg transition-all duration-300 ease-out ${getPositionClass()} ${
            isLocked ? 'opacity-75' : ''
          }`}
        />
        
        {/* Toggle Options */}
        <div className="relative flex h-full">
          {options.map((option, index) => (
            <button
              key={option.value}
              onClick={() => handleToggleClick(option.value)}
              disabled={isLocked}
              className={`flex-1 flex items-center justify-center text-xs font-medium transition-all duration-300 rounded-full ${
                isLocked 
                  ? 'cursor-not-allowed opacity-75' 
                  : 'cursor-pointer'
              } ${
                value === option.value
                  ? 'text-gray-900'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

export default AppleToggle