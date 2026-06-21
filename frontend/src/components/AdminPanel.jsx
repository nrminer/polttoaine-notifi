import React, { useState } from 'react';
import { AlertCircle, CheckCircle, Settings, X } from 'lucide-react';
import { fixCapture, triggerAdminAction, runTrackingAll, testNotification } from '../lib/api';
import { fmtPrice } from '../lib/utils';

export default function AdminPanel({ onClose }) {
  const [token, setToken] = useState(() => {
    const stored = localStorage.getItem('admin_token');
    const expiry = localStorage.getItem('admin_token_expiry');
    
    // Check if token expired (24 hour expiry)
    if (stored && expiry) {
      const expiryTime = new Date(expiry);
      if (new Date() > expiryTime) {
        localStorage.removeItem('admin_token');
        localStorage.removeItem('admin_token_expiry');
        return '';
      }
      return stored;
    }
    return '';
  });
  const [activeTab, setActiveTab] = useState('fix');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  // Fix capture form
  const [fixForm, setFixForm] = useState({
    date: new Date().toISOString().split('T')[0],
    hour: 21,
    fuel: '95E10',
    correctedPrice: '',
    reason: ''
  });

  // Admin action form
  const [actionForm, setActionForm] = useState({
    action: 'capture',
    fuel: '95E10',
    notify: false
  });

  const saveToken = (newToken) => {
    setToken(newToken);
    if (newToken) {
      localStorage.setItem('admin_token', newToken);
      // Set expiry to 24 hours from now
      const expiry = new Date();
      expiry.setHours(expiry.getHours() + 24);
      localStorage.setItem('admin_token_expiry', expiry.toISOString());
    } else {
      localStorage.removeItem('admin_token');
      localStorage.removeItem('admin_token_expiry');
    }
  };

  const handleFixCapture = async (e) => {
    e.preventDefault();
    if (!token) {
      setError('Admin token vaaditaan');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await fixCapture(
        token,
        fixForm.date,
        parseInt(fixForm.hour),
        fixForm.fuel,
        parseFloat(fixForm.correctedPrice),
        fixForm.reason
      );
      setResult({
        type: 'success',
        message: `Korjattu: ${fmtPrice(data.original_price)} → ${fmtPrice(data.corrected_price)}`
      });
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleAdminAction = async (e) => {
    e.preventDefault();
    if (!token) {
      setError('Admin token vaaditaan');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await triggerAdminAction(
        token,
        actionForm.action,
        actionForm.fuel,
        actionForm.notify
      );
      setResult({
        type: 'success',
        message: `Toiminto "${actionForm.action}" suoritettu`,
        data
      });
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleTestNotification = async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      await testNotification();
      setResult({
        type: 'success',
        message: 'Testi-ilmoitus lähetetty'
      });
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleRunTracking = async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await runTrackingAll(true);
      setResult({
        type: 'success',
        message: 'Tallennukset suoritettu',
        data
      });
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-200 dark:border-slate-700">
          <div className="flex items-center gap-3">
            <Settings className="w-6 h-6 text-brand" />
            <h2 className="text-xl font-bold text-ink">Ylläpitopaneeli</h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-secondary" />
          </button>
        </div>

        {/* Token Input */}
        <div className="p-6 border-b border-slate-200 dark:border-slate-700">
          <label className="block text-sm font-medium text-secondary mb-2">
            Admin Token
          </label>
          <input
            type="password"
            value={token}
            onChange={(e) => saveToken(e.target.value)}
            placeholder="Syötä admin token"
            className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-ink focus:outline-none focus:ring-2 focus:ring-brand"
          />
        </div>

        {/* Tabs */}
        <div className="flex border-b border-slate-200 dark:border-slate-700">
          <button
            onClick={() => setActiveTab('fix')}
            className={`flex-1 px-6 py-3 font-medium transition-colors ${
              activeTab === 'fix'
                ? 'text-brand border-b-2 border-brand bg-blue-50 dark:bg-slate-900'
                : 'text-secondary hover:text-ink'
            }`}
          >
            Korjaa Tallennus
          </button>
          <button
            onClick={() => setActiveTab('actions')}
            className={`flex-1 px-6 py-3 font-medium transition-colors ${
              activeTab === 'actions'
                ? 'text-brand border-b-2 border-brand bg-blue-50 dark:bg-slate-900'
                : 'text-secondary hover:text-ink'
            }`}
          >
            Toiminnot
          </button>
          <button
            onClick={() => setActiveTab('quick')}
            className={`flex-1 px-6 py-3 font-medium transition-colors ${
              activeTab === 'quick'
                ? 'text-brand border-b-2 border-brand bg-blue-50 dark:bg-slate-900'
                : 'text-secondary hover:text-ink'
            }`}
          >
            Pikatoiminnot
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Fix Capture Tab */}
          {activeTab === 'fix' && (
            <form onSubmit={handleFixCapture} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-secondary mb-2">
                    Päivämäärä
                  </label>
                  <input
                    type="date"
                    value={fixForm.date}
                    onChange={(e) => setFixForm({ ...fixForm, date: e.target.value })}
                    className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-ink"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-secondary mb-2">
                    Tunti
                  </label>
                  <select
                    value={fixForm.hour}
                    onChange={(e) => setFixForm({ ...fixForm, hour: e.target.value })}
                    className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-ink"
                    required
                  >
                    <option value="14">14:00</option>
                    <option value="21">21:00</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-secondary mb-2">
                    Polttoaine
                  </label>
                  <select
                    value={fixForm.fuel}
                    onChange={(e) => setFixForm({ ...fixForm, fuel: e.target.value })}
                    className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-ink"
                    required
                  >
                    <option value="95E10">95E10</option>
                    <option value="diesel">Diesel</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-secondary mb-2">
                    Korjattu Hinta (€)
                  </label>
                  <input
                    type="number"
                    step="0.001"
                    value={fixForm.correctedPrice}
                    onChange={(e) => setFixForm({ ...fixForm, correctedPrice: e.target.value })}
                    placeholder="1.878"
                    className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-ink"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-secondary mb-2">
                  Syy
                </label>
                <input
                  type="text"
                  value={fixForm.reason}
                  onChange={(e) => setFixForm({ ...fixForm, reason: e.target.value })}
                  placeholder="Virheellinen skrappaus"
                  className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-ink"
                  required
                />
              </div>

              <button
                type="submit"
                disabled={loading || !token}
                className="w-full px-6 py-3 bg-brand hover:bg-blue-700 text-white font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Korjataan...' : 'Korjaa Tallennus'}
              </button>
            </form>
          )}

          {/* Admin Actions Tab */}
          {activeTab === 'actions' && (
            <form onSubmit={handleAdminAction} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-secondary mb-2">
                  Toiminto
                </label>
                <select
                  value={actionForm.action}
                  onChange={(e) => setActionForm({ ...actionForm, action: e.target.value })}
                  className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-ink"
                  required
                >
                  <option value="ping">Ping (testi)</option>
                  <option value="capture">Tallenna hinnat</option>
                  <option value="predict">Päivitä ennusteet</option>
                  <option value="all">Tallenna + Ennusta</option>
                  <option value="notify">Lähetä ilmoitus</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-secondary mb-2">
                  Polttoaine
                </label>
                <select
                  value={actionForm.fuel}
                  onChange={(e) => setActionForm({ ...actionForm, fuel: e.target.value })}
                  className="w-full px-4 py-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg text-ink"
                  required
                >
                  <option value="all">Molemmat</option>
                  <option value="95E10">95E10</option>
                  <option value="diesel">Diesel</option>
                </select>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="notify"
                  checked={actionForm.notify}
                  onChange={(e) => setActionForm({ ...actionForm, notify: e.target.checked })}
                  className="w-4 h-4 text-brand rounded"
                />
                <label htmlFor="notify" className="text-sm text-secondary">
                  Lähetä ilmoitus (vain capture/all)
                </label>
              </div>

              <button
                type="submit"
                disabled={loading || !token}
                className="w-full px-6 py-3 bg-brand hover:bg-blue-700 text-white font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Suoritetaan...' : 'Suorita Toiminto'}
              </button>
            </form>
          )}

          {/* Quick Actions Tab */}
          {activeTab === 'quick' && (
            <div className="space-y-3">
              <button
                onClick={handleRunTracking}
                disabled={loading}
                className="w-full px-6 py-3 bg-green-600 hover:bg-green-700 text-white font-medium rounded-lg transition-colors disabled:opacity-50"
              >
                {loading ? 'Suoritetaan...' : 'Tallenna Kaikki + Ilmoitus'}
              </button>

              <button
                onClick={handleTestNotification}
                disabled={loading}
                className="w-full px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white font-medium rounded-lg transition-colors disabled:opacity-50"
              >
                {loading ? 'Lähetetään...' : 'Lähetä Testi-ilmoitus'}
              </button>

              <div className="mt-6 p-4 bg-slate-50 dark:bg-slate-900 rounded-lg">
                <h3 className="text-sm font-medium text-secondary mb-2">Huom:</h3>
                <ul className="text-sm text-muted space-y-1">
                  <li>• Pikatoiminnot eivät vaadi admin tokenia</li>
                  <li>• Tallenna Kaikki hakee molemmat polttoaineet</li>
                  <li>• Testi-ilmoitus käyttää viimeisimpiä tallennuksia</li>
                </ul>
              </div>
            </div>
          )}

          {/* Result/Error Messages */}
          {result && (
            <div className="mt-6 p-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
              <div className="flex items-start gap-3">
                <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-green-900 dark:text-green-100">
                    {result.message}
                  </p>
                  {result.data && (
                    <pre className="mt-2 text-xs text-green-700 dark:text-green-300 overflow-auto">
                      {JSON.stringify(result.data, null, 2)}
                    </pre>
                  )}
                </div>
              </div>
            </div>
          )}

          {error && (
            <div className="mt-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
              <div className="flex items-start gap-3">
                <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-red-900 dark:text-red-100">Virhe</p>
                  <p className="mt-1 text-sm text-red-700 dark:text-red-300">{error}</p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
