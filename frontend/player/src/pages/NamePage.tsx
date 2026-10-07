import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '../lib/api';
import { isTokenExpired } from '../lib/utils';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Card, CardContent, CardHeader } from '../components/ui/card';

type Mode = 'guest' | 'netid' | 'local';

export default function NamePage() {
  const { code = '' } = useParams<{ code: string }>();
  const navigate = useNavigate();

  // Only treat the token as valid if it is present AND not expired
  const isAuthenticated = !isTokenExpired(localStorage.getItem('token'));
  const [mode, setMode] = useState<Mode>(isAuthenticated ? 'netid' : 'guest');

  // Guest fields — pre-fill from localStorage if available
  const [displayName, setDisplayName] = useState(() => localStorage.getItem('playerName') ?? '');
  const [email, setEmail] = useState(() => localStorage.getItem('playerEmail') ?? '');

  // Login fields
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleGuest(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await api.post<{ access_token: string }>('/auth/guest', {
        display_name: displayName.trim(),
        email: email.trim().toLowerCase(),
        room_code: code,
      });
      localStorage.setItem('token', data.access_token);
      localStorage.setItem('playerName', displayName.trim());
      localStorage.setItem('playerEmail', email.trim().toLowerCase());
      navigate(`/game/${code}/lobby`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to join');
    } finally {
      setLoading(false);
    }
  }

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await api.post<{ access_token: string }>('/auth/login', { username, password });
      localStorage.setItem('token', data.access_token);
      navigate(`/game/${code}/lobby`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid credentials');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <h1 className="text-xl font-bold text-fg text-center">Join Room {code}</h1>

          {/* Mode toggle — hidden when already authenticated */}
          {!isAuthenticated && (
            <div className="flex mt-3 bg-surface-raised rounded-xl p-1 gap-1">
              <button
                type="button"
                onClick={() => { setMode('guest'); setError(''); }}
                className={`flex-1 min-h-11 py-2 rounded-lg text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page ${
                  mode === 'guest'
                    ? 'bg-accent text-on-accent'
                    : 'text-fg-muted hover:text-fg'
                }`}
              >
                Join as Guest
              </button>
              <button
                type="button"
                onClick={() => { setMode('netid'); setError(''); }}
                className={`flex-1 min-h-11 py-2 rounded-lg text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page ${
                  mode === 'netid' || mode === 'local'
                    ? 'bg-accent text-on-accent'
                    : 'text-fg-muted hover:text-fg'
                }`}
              >
                Sign In
              </button>
            </div>
          )}
        </CardHeader>

        <CardContent>
          {mode === 'guest' && (
            <form onSubmit={handleGuest} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-fg-muted mb-1">Display Name</label>
                <Input
                  type="text"
                  value={displayName}
                  onChange={e => setDisplayName(e.target.value)}
                  placeholder="Your name"
                  maxLength={50}
                  required
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-fg-muted mb-1">Email</label>
                <Input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  required
                />
              </div>
              {error && <p className="text-danger-text text-sm text-center">{error}</p>}
              <Button
                type="submit"
                className="w-full"
                size="lg"
                disabled={loading || !displayName.trim() || !email.trim()}
              >
                {loading ? 'Joining…' : 'Join Game'}
              </Button>
            </form>
          )}

          {mode === 'netid' && (
            <div className="space-y-3">
              {isAuthenticated ? (
                /* Already signed in via OAuth2 — go straight to lobby */
                <Button
                  className="w-full"
                  size="lg"
                  onClick={() => navigate(`/game/${code}/lobby`)}
                >
                  Join Game
                </Button>
              ) : (
                /* Trigger OAuth2 — save room code so we can return here after auth */
                <a
                  href="/api/auth/oauth2-callback?redirect_to=/player/login"
                  onClick={() => sessionStorage.setItem('joinRoomCode', code)}
                  className="flex items-center justify-center w-full py-3 px-4 rounded-xl font-medium bg-accent hover:bg-accent-hover text-on-accent transition-colors focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page"
                >
                  Sign in with UW NetID
                </a>
              )}
              {error && <p className="text-danger-text text-sm text-center">{error}</p>}
              {!isAuthenticated && (
                <button
                  type="button"
                  onClick={() => { setMode('local'); setError(''); }}
                  className="w-full text-fg-subtle text-sm hover:text-fg-muted transition-colors focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page"
                >
                  Use local account instead
                </button>
              )}
            </div>
          )}

          {mode === 'local' && (
            <form onSubmit={handleLogin} className="space-y-4">
              <Input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="Username"
                autoComplete="username"
                required
                autoFocus
              />
              <Input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Password"
                autoComplete="current-password"
                required
              />
              {error && <p className="text-danger-text text-sm text-center">{error}</p>}
              <Button
                type="submit"
                className="w-full"
                size="lg"
                disabled={loading || !username || !password}
              >
                {loading ? 'Signing in…' : 'Sign In & Join'}
              </Button>
              <button
                type="button"
                onClick={() => { setMode('netid'); setError(''); }}
                className="w-full text-fg-subtle text-sm hover:text-fg-muted transition-colors focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page"
              >
                ← Back to NetID sign in
              </button>
            </form>
          )}

          <button
            type="button"
            onClick={() => navigate('/join')}
            className="w-full mt-3 min-h-11 rounded-xl text-fg-subtle text-sm hover:text-fg-muted transition-colors focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page"
          >
            ← Different room code
          </button>
        </CardContent>
      </Card>
    </div>
  );
}
