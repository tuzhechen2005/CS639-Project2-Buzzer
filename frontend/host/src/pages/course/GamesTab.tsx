import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Copy, List, Lock, Play, Plus, Trash2, Upload } from 'lucide-react';
import { api } from '../../lib/api';
import { Button } from '../../components/ui/button';
import { Card, CardContent, CardHeader } from '../../components/ui/card';
import { Input } from '../../components/ui/input';
import { useCourse } from './CourseLayout';

export interface Game {
  id: number;
  course_id: number;
  title: string;
  description: string;
  max_players: number;
  created_at: string;
  locked: boolean;
}

export default function GamesTab() {
  const course = useCourse();
  const navigate = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);
  const [games, setGames] = useState<Game[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [maxPlayers, setMaxPlayers] = useState('150');
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);

  const editorPath = (gameId: number) => `/courses/${course.id}/games/${gameId}/questions`;

  async function load() {
    try {
      setGames(await api.get<Game[]>(`/courses/${course.id}/games`));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load games');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [course.id]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      const game = await api.post<Game>(`/courses/${course.id}/games`, {
        title,
        description,
        max_players: Number(maxPlayers),
      });
      navigate(editorPath(game.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create game');
      setSaving(false);
    }
  }

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setError('');
    try {
      const form = new FormData();
      form.append('file', file);
      const game = await api.postForm<Game>(`/courses/${course.id}/games/import`, form);
      navigate(editorPath(game.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed');
      setImporting(false);
    } finally {
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  async function startRoom(game: Game) {
    setBusyId(game.id);
    setError('');
    try {
      const data = await api.post<{ room_code: string }>('/game/rooms', {
        course_id: course.id,
        game_id: game.id,
      });
      navigate(`/game/${data.room_code}/lobby`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create room');
      setBusyId(null);
    }
  }

  async function duplicate(game: Game) {
    setBusyId(game.id);
    setError('');
    try {
      const copy = await api.post<Game>(`/games/${game.id}/duplicate`);
      navigate(editorPath(copy.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to duplicate game');
      setBusyId(null);
    }
  }

  async function deleteGame(game: Game) {
    if (!confirm(`Delete "${game.title}"? This deletes the game and any unplayed sessions.`)) return;
    setBusyId(game.id);
    setError('');
    try {
      await api.delete(`/games/${game.id}`);
      setGames((prev) => prev.filter((g) => g.id !== game.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete game');
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-fg">Games</h2>
        <div className="flex gap-2">
          <input ref={fileRef} type="file" accept=".json" className="hidden" onChange={handleImport} />
          <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()} disabled={importing}>
            <Upload size={14} className="mr-1" />
            {importing ? 'Importing…' : 'Import JSON'}
          </Button>
          <Button size="sm" onClick={() => setShowForm(!showForm)}>
            <Plus size={16} className="mr-1" /> New Game
          </Button>
        </div>
      </div>

      {error && <p className="text-danger-text text-sm">{error}</p>}

      {showForm && (
        <Card>
          <CardHeader><h3 className="text-lg font-semibold text-fg">Create Game</h3></CardHeader>
          <CardContent>
            <form onSubmit={handleCreate} className="space-y-3">
              <Input placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} required />
              <textarea
                placeholder="Description (optional)"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full rounded-lg border border-line-strong bg-surface-raised px-3 py-2 text-fg placeholder:text-fg-subtle focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page resize-none"
                rows={3}
              />
              <div>
                <label className="block text-xs text-fg-muted mb-1">Max players</label>
                <Input
                  type="number"
                  value={maxPlayers}
                  onChange={(e) => setMaxPlayers(e.target.value)}
                  min="1"
                  max="500"
                  className="w-32"
                />
              </div>
              <div className="flex gap-3">
                <Button type="submit" disabled={saving}>{saving ? 'Creating…' : 'Create and add questions'}</Button>
                <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>Cancel</Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <p className="text-fg-muted">Loading…</p>
      ) : games.length === 0 ? (
        <p className="text-fg-muted">
          No games yet. Create one, or ask an admin to grant you access to this course's existing games.
        </p>
      ) : (
        <div className="space-y-3">
          {games.map((g) => (
            <Card key={g.id} className="flex items-center justify-between gap-4 px-6 py-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="font-semibold text-fg truncate">{g.title}</p>
                  {g.locked && (
                    <span
                      className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-warning-subtle text-warning-text"
                      title="This game has recorded answers, so its questions can't change. Duplicate it to edit."
                    >
                      <Lock size={11} /> Played — locked
                    </span>
                  )}
                </div>
                {g.description && <p className="text-fg-muted text-sm mt-0.5 line-clamp-1">{g.description}</p>}
                <p className="text-fg-subtle text-xs mt-0.5">Max {g.max_players} players</p>
              </div>
              <div className="flex gap-2 shrink-0">
                <Button size="sm" onClick={() => void startRoom(g)} disabled={busyId === g.id}>
                  <Play size={14} className="mr-1" /> Start room
                </Button>
                {g.locked ? (
                  <Button variant="outline" size="sm" onClick={() => void duplicate(g)} disabled={busyId === g.id}>
                    <Copy size={14} className="mr-1" /> Duplicate to edit
                  </Button>
                ) : (
                  <>
                    <Button variant="outline" size="sm" onClick={() => navigate(editorPath(g.id))}>
                      <List size={14} className="mr-1" /> Edit questions
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => void deleteGame(g)}
                      disabled={busyId === g.id}
                      title="Delete game"
                    >
                      <Trash2 size={14} />
                    </Button>
                  </>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
