import React from 'react'
import { ArrowLeft, Calendar, Edit } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

const Appointments = () => {
  const navigate = useNavigate()

  return (
    <div className="space-y-6">
      {/* Header with Back Button */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <button
            onClick={() => navigate('/')}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="h-5 w-5 text-gray-600" />
          </button>
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Appointments</h1>
            <p className="text-gray-600 mt-1">View and manage appointments directly in Google Calendar</p>
          </div>
        </div>
        <div className="flex items-center space-x-3">
          <a
            href="https://calendar.google.com/"
            target="_blank"
            rel="noopener noreferrer"
            className="btn-primary flex items-center space-x-2"
          >
            <Edit className="h-4 w-4" />
            <span>Edit in Google Calendar</span>
          </a>
        </div>
      </div>

      {/* Calendar Embed */}
      <div className="card p-0 overflow-hidden">
        <div className="bg-gray-50 px-6 py-4 border-b border-gray-200">
          <div className="flex items-center space-x-3">
            <Calendar className="h-5 w-5 text-primary-600" />
            <h2 className="text-lg font-semibold text-gray-900">Omorfia Med Spa Calendar</h2>
          </div>
          <p className="text-sm text-gray-600 mt-1">
            View-only calendar below. To make changes, click "Edit in Google Calendar" above.
          </p>
        </div>
        
        <div className="relative">
          <iframe 
            src="https://calendar.google.com/calendar/embed?height=700&wkst=1&ctz=America%2FDetroit&mode=WEEK&showTitle=0&showPrint=0&src=NmM0N2ZhYzEyOTk1MzA5NmFiYmQzMjgxNTQxMjM0YzRiMzE1OGY0NGJlZGI3ZWVlYjdkNmY1MmM2MWRjYTNjN0Bncm91cC5jYWxlbmRhci5nb29nbGUuY29t&color=%23c0ca33"
            style={{ border: 'solid 1px #777' }}
            width="1400"
            height="700"
            frameBorder="0"
            scrolling="no"
            className="w-full"
            title="Omorfia Med Spa Calendar"
          />
        </div>
      </div>

      {/* Help Section */}
      <div className="card bg-blue-50 border-blue-200">
        <div className="flex items-start space-x-3">
          <div className="bg-blue-100 rounded-full p-2 mt-1">
            <Calendar className="h-5 w-5 text-blue-600" />
          </div>
          <div>
            <h3 className="font-semibold text-blue-900 mb-2">How to Manage Appointments</h3>
            <div className="space-y-3">
              <div>
                <h4 className="font-medium text-blue-800 mb-1">📅 View Appointments</h4>
                <p className="text-sm text-blue-700">Use the embedded calendar below to see all scheduled appointments in week view (read-only format).</p>
              </div>
              <div>
                <h4 className="font-medium text-blue-800 mb-1">✏️ Edit, Move, or Cancel Appointments</h4>
                <p className="text-sm text-blue-700">Click the "Edit in Google Calendar" button above to access the full Google Calendar interface where you can:</p>
                <ul className="text-sm text-blue-700 ml-4 mt-1 space-y-1">
                  <li>• Edit appointment details</li>
                  <li>• Move appointments to different times</li>
                  <li>• Cancel or delete appointments</li>
                  <li>• Create new appointments manually</li>
                </ul>
              </div>
              <div>
                <h4 className="font-medium text-blue-800 mb-1">🔐 Sign In Required</h4>
                <p className="text-sm text-blue-700">You'll need to sign in to your Google account to make changes to the calendar.</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Appointments