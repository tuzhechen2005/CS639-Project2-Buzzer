import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader } from '../components/ui/card';

interface Course { id: number; name: string; semester: string }
interface ActiveSession {
  session_id: string;
  room_code: string;
  status: string;
  game_title: string;
  course_name: string;
  course_semester: string;
}

/** Course picker: the host chooses a course, then manages and runs its games there. */
export default function HomePage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [activeSessions, setActiveSessions] = useState<ActiveSession[]>([]);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([
      api.get<Course[]>('/game/my-courses'),
      api.get<ActiveSession[]>('/game/my-active-sessions'),
    ]).then(([c, s]) => {
      setCourses(c);
      setActiveSessions(s);
    }).catch((err) => {
      setError(err instanceof Error ? err.message : 'Failed to load courses. Are you still logged in?');
    }).finally(() => setLoading(false));
  }, []);

  async function deleteSession(sessionId: string) {
    try {
      await api.delete(`/game/sessions/${sessionId}`);
      setActiveSessions(prev => prev.filter(s => s.session_id !== sessionId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete session');
    } finally {
      setConfirmDelete(null);
    }
  }

  function logout() {
    localStorage.removeItem('token');
    navigate('/login');
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4 gap-4">
      {activeSessions.length > 0 && (
        <Card className="w-full max-w-lg border-amber-500/40">
          <CardHeader>
            <h2 className="text-lg font-semibold text-amber-400">Active Sessions</h2>
            <p className="text-slate-400 text-sm">You have running games — rejoin one or pick a course below.</p>
          </CardHeader>
          <CardContent className="space-y-2">
            {activeSessions.map(s => (
              <div
                key={s.session_id}
                className="flex items-center justify-between rounded-lg bg-slate-800 border border-slate-700 px-4 py-3"
              >
                <div>
                  <p className="text-slate-100 font-medium">{s.game_title}</p>
                  <p className="text-slate-400 text-sm">{s.course_name} · {s.course_semester}</p>
                  <p className="text-slate-500 text-xs mt-0.5">
                    Room <span className="font-mono text-slate-300">{s.room_code}</span>
                    {' · '}
                    <span className={s.status === 'IN_PROGRESS' ? 'text-green-400' : 'text-amber-400'}>
                      {s.status === 'IN_PROGRESS' ? 'In Progress' : 'Lobby'}
                    </span>
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {confirmDelete === s.session_id ? (
                    <>
                      <span className="text-red-400 text-xs max-w-[11rem] text-right">
                        Recorded scores (grades) will be permanently deleted.
                      </span>
                      <Button size="sm" variant="destructive" onClick={() => void deleteSession(s.session_id)}>
                        Delete
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(null)}>
                        Cancel
                      </Button>
                    </>
                  ) : (
                    <>
                      <Button size="sm" variant="outline" onClick={() => navigate(`/game/${s.room_code}/lobby`)}>
                        Rejoin
                      </Button>
                      <Button size="sm" variant="destructive" onClick={() => setConfirmDelete(s.session_id)}>
                        Delete
                      </Button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Card className="w-full max-w-lg">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-slate-100">Your Courses</h1>
              <p className="text-slate-400 text-sm mt-1">Pick a course to manage its games, roster and past sessions</p>
            </div>
            <Button variant="ghost" size="sm" onClick={logout}>Sign Out</Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          {error && <p className="text-red-400 text-sm">{error}</p>}
          {loading ? (
            <p className="text-slate-400 text-sm">Loading…</p>
          ) : courses.length === 0 ? (
            <p className="text-slate-400 text-sm">
              You are not a host of any course yet. Ask an admin to grant you HOST access to a course.
            </p>
          ) : (
            courses.map(c => (
              <button
                key={c.id}
                onClick={() => navigate(`/courses/${c.id}/games`)}
                className="w-full flex items-center justify-between rounded-lg bg-slate-800 border border-slate-700 px-4 py-3 text-left hover:border-indigo-500 transition-colors"
              >
                <div>
                  <p className="text-slate-100 font-medium">{c.name}</p>
                  <p className="text-slate-400 text-sm">{c.semester}</p>
                </div>
                <ChevronRight size={18} className="text-slate-500" />
              </button>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
