import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Users, Pencil, Trash2, Lock, ArrowRight } from 'lucide-react';
import { api } from '../lib/api';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader } from '../components/ui/card';
import { Input } from '../components/ui/input';

interface Course {
  id: number;
  name: string;
  semester: string;
  is_system: boolean;
  created_at: string;
}

interface Game {
  id: number;
  course_id: number;
  title: string;
  locked: boolean;
}

interface CourseAccessItem {
  user_id: string;
  display_name: string | null;
  netid: string | null;
  username: string | null;
  role: 'HOST' | 'PLAYER';
}

function accessName(a: CourseAccessItem): string {
  return a.display_name ?? a.username ?? a.netid ?? a.user_id;
}

export default function CoursesPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [games, setGames] = useState<Game[]>([]);
  const [access, setAccess] = useState<Record<number, CourseAccessItem[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState('');
  const [semester, setSemester] = useState('');
  const [saving, setSaving] = useState(false);
  const [editingCourse, setEditingCourse] = useState<Course | null>(null);
  const [editName, setEditName] = useState('');
  const [editSemester, setEditSemester] = useState('');
  const [editSaving, setEditSaving] = useState(false);
  const [moveTarget, setMoveTarget] = useState<Record<number, string>>({});
  const [busyGameId, setBusyGameId] = useState<number | null>(null);

  async function load() {
    try {
      const [cs, gs] = await Promise.all([
        api.get<Course[]>('/admin/courses'),
        api.get<Game[]>('/admin/games'),
      ]);
      const real = cs.filter((c) => !c.is_system);
      const lists = await Promise.all(
        real.map((c) => api.get<CourseAccessItem[]>(`/admin/courses/${c.id}/access`)),
      );
      setCourses(cs);
      setGames(gs);
      setAccess(Object.fromEntries(real.map((c, i) => [c.id, lists[i]])));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load courses');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await api.post('/admin/courses', { name, semester });
      setName('');
      setSemester('');
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create course');
    } finally {
      setSaving(false);
    }
  }

  function startEdit(c: Course) {
    setEditingCourse(c);
    setEditName(c.name);
    setEditSemester(c.semester);
    setShowForm(false);
  }

  async function handleEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!editingCourse) return;
    setEditSaving(true);
    setError('');
    try {
      await api.put(`/admin/courses/${editingCourse.id}`, {
        name: editName,
        semester: editSemester,
      });
      setEditingCourse(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update course');
    } finally {
      setEditSaving(false);
    }
  }

  async function moveGame(game: Game) {
    const target = moveTarget[game.id];
    if (!target) return;
    setBusyGameId(game.id);
    setError('');
    try {
      await api.put(`/admin/games/${game.id}`, { course_id: Number(target) });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to move game');
    } finally {
      setBusyGameId(null);
    }
  }

  async function deleteGame(game: Game) {
    const warning = game.locked
      ? `Delete "${game.title}"? It has been played: all its sessions and their recorded scores (grades) will be permanently deleted.`
      : `Delete "${game.title}" and any unplayed sessions?`;
    if (!confirm(warning)) return;
    setBusyGameId(game.id);
    setError('');
    try {
      await api.delete(`/admin/games/${game.id}`);
      setGames((prev) => prev.filter((g) => g.id !== game.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete game');
    } finally {
      setBusyGameId(null);
    }
  }

  const realCourses = courses.filter((c) => !c.is_system);
  const systemIds = new Set(courses.filter((c) => c.is_system).map((c) => c.id));
  const unassignedGames = games.filter((g) => systemIds.has(g.course_id));

  function gameRow(g: Game, extra?: React.ReactNode) {
    return (
      <div key={g.id} className="flex items-center justify-between gap-3 py-1.5">
        <span className="flex items-center gap-2 text-sm text-slate-200 min-w-0">
          <span className="truncate">{g.title}</span>
          {g.locked && (
            <span className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-amber-900/50 text-amber-300 shrink-0">
              <Lock size={10} /> played
            </span>
          )}
        </span>
        <div className="flex items-center gap-2 shrink-0">
          {extra}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void deleteGame(g)}
            disabled={busyGameId === g.id}
            title="Delete game"
          >
            <Trash2 size={12} />
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-slate-100">Courses</h2>
        <Button onClick={() => { setShowForm(!showForm); setEditingCourse(null); }} size="sm">
          <Plus size={16} className="mr-1" /> New Course
        </Button>
      </div>

      {error && <p className="text-red-400 mb-4 text-sm">{error}</p>}

      {showForm && (
        <Card className="mb-6">
          <CardHeader><h3 className="text-lg font-semibold text-slate-100">Create Course</h3></CardHeader>
          <CardContent>
            <form onSubmit={handleCreate} className="flex gap-3 flex-wrap">
              <Input
                placeholder="Course name (e.g. CS 537)"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="flex-1 min-w-48"
                required
              />
              <Input
                placeholder="Semester (e.g. Fall 2026)"
                value={semester}
                onChange={(e) => setSemester(e.target.value)}
                className="flex-1 min-w-48"
                required
              />
              <Button type="submit" disabled={saving}>{saving ? 'Creating…' : 'Create'}</Button>
              <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>Cancel</Button>
            </form>
          </CardContent>
        </Card>
      )}

      {editingCourse && (
        <Card className="mb-6">
          <CardHeader><h3 className="text-lg font-semibold text-slate-100">Edit Course</h3></CardHeader>
          <CardContent>
            <form onSubmit={handleEdit} className="flex gap-3 flex-wrap">
              <Input
                placeholder="Course name"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                className="flex-1 min-w-48"
                required
              />
              <Input
                placeholder="Semester"
                value={editSemester}
                onChange={(e) => setEditSemester(e.target.value)}
                className="flex-1 min-w-48"
                required
              />
              <Button type="submit" disabled={editSaving}>{editSaving ? 'Saving…' : 'Save'}</Button>
              <Button type="button" variant="ghost" onClick={() => setEditingCourse(null)}>Cancel</Button>
            </form>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <p className="text-slate-400">Loading…</p>
      ) : (
        <div className="space-y-4">
          {unassignedGames.length > 0 && (
            <Card className="border-amber-500/40">
              <CardHeader>
                <h3 className="font-semibold text-amber-400">Unassigned games</h3>
                <p className="text-slate-400 text-sm">
                  These games had no course after the upgrade. They can't be run until you move each one
                  to a course; its HOSTs then get access to it.
                </p>
              </CardHeader>
              <CardContent className="divide-y divide-slate-700/60">
                {unassignedGames.map((g) => gameRow(g, (
                  <>
                    <select
                      value={moveTarget[g.id] ?? ''}
                      onChange={(e) => setMoveTarget((prev) => ({ ...prev, [g.id]: e.target.value }))}
                      className="rounded-lg border border-slate-600 bg-slate-800 px-2 py-1 text-sm text-slate-100"
                    >
                      <option value="">Move to course…</option>
                      {realCourses.map((c) => (
                        <option key={c.id} value={c.id}>{c.name} — {c.semester}</option>
                      ))}
                    </select>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void moveGame(g)}
                      disabled={!moveTarget[g.id] || busyGameId === g.id}
                    >
                      <ArrowRight size={12} className="mr-1" /> Move
                    </Button>
                  </>
                )))}
              </CardContent>
            </Card>
          )}

          {realCourses.length === 0 ? (
            <p className="text-slate-400">No courses yet. Create one above.</p>
          ) : realCourses.map((c) => {
            const grants = access[c.id] ?? [];
            const hosts = grants.filter((a) => a.role === 'HOST');
            const players = grants.filter((a) => a.role === 'PLAYER');
            const courseGames = games.filter((g) => g.course_id === c.id);
            return (
              <Card key={c.id}>
                <CardHeader>
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="font-semibold text-slate-100">{c.name}</p>
                      <p className="text-slate-400 text-sm">{c.semester}</p>
                    </div>
                    <div className="flex gap-2 shrink-0">
                      <Button variant="outline" size="sm" onClick={() => startEdit(c)} title="Edit course">
                        <Pencil size={14} />
                      </Button>
                      {/* The roster editor lives in the host app (works behind nginx on :8080). */}
                      <a
                        href={`/host/courses/${c.id}/roster`}
                        className="inline-flex items-center justify-center rounded-lg font-semibold transition-colors border border-slate-600 text-slate-200 hover:bg-slate-700 px-3 py-1.5 text-sm"
                      >
                        <Users size={14} className="mr-1" /> Roster
                      </a>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="grid gap-4 md:grid-cols-3 text-sm">
                  <div>
                    <p className="text-xs uppercase tracking-wider text-slate-500 mb-1">Hosts</p>
                    {hosts.length === 0 ? (
                      <p className="text-slate-500">None</p>
                    ) : hosts.map((a) => (
                      <Link key={a.user_id} to={`/users/${a.user_id}`} className="block text-slate-200 hover:text-indigo-300">
                        {accessName(a)}
                      </Link>
                    ))}
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-wider text-slate-500 mb-1">Players (explicit access)</p>
                    {players.length === 0 ? (
                      <p className="text-slate-500">None</p>
                    ) : players.map((a) => (
                      <Link key={a.user_id} to={`/users/${a.user_id}`} className="block text-slate-200 hover:text-indigo-300">
                        {accessName(a)}
                      </Link>
                    ))}
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-wider text-slate-500 mb-1">Games</p>
                    {courseGames.length === 0 ? (
                      <p className="text-slate-500">None</p>
                    ) : (
                      <div className="divide-y divide-slate-700/60">
                        {courseGames.map((g) => gameRow(g))}
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
