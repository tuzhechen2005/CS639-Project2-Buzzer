import { useEffect, useState } from 'react';
import { ChevronDown, ChevronUp, Download, FileText } from 'lucide-react';
import { api } from '../../lib/api';
import { Button } from '../../components/ui/button';
import { Card } from '../../components/ui/card';
import { Input } from '../../components/ui/input';
import { useCourse } from './CourseLayout';

interface SessionItem {
  session_id: string;
  room_code: string;
  status: string;
  game_id: number;
  game_title: string;
  course_id: number;
  course_name: string;
  course_semester: string;
  host_display_name: string | null;
  created_at: string;
  completed_at: string | null;
  player_count: number;
}

interface CanvasOptions {
  title: string;
  assignmentId: string;
  sisDomain: string;
  rosterOnly: boolean;
  perQuestion: boolean;
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

/**
 * Finished (completed or abandoned) sessions of the course, with the HTML summary,
 * per-player score CSV and Canvas gradebook CSV. Downloads only: deleting a session
 * deletes grades, so it is not offered here.
 */
export default function SessionsTab() {
  const course = useCourse();
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [canvasOpenId, setCanvasOpenId] = useState<string | null>(null);
  const [canvasOpts, setCanvasOpts] = useState<Record<string, CanvasOptions>>({});

  useEffect(() => {
    setLoading(true);
    api.get<SessionItem[]>(`/courses/${course.id}/sessions`)
      .then(setSessions)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load sessions'))
      .finally(() => setLoading(false));
  }, [course.id]);

  function getOpts(s: SessionItem): CanvasOptions {
    return canvasOpts[s.session_id] ?? {
      title: s.game_title,
      assignmentId: '',
      sisDomain: 'wisc.edu',
      rosterOnly: true,
      perQuestion: false,
    };
  }

  function setOpt<K extends keyof CanvasOptions>(s: SessionItem, key: K, val: CanvasOptions[K]) {
    setCanvasOpts((prev) => ({ ...prev, [s.session_id]: { ...getOpts(s), [key]: val } }));
  }

  async function download(key: string, path: string) {
    setBusy(key);
    setError('');
    try {
      await api.download(path);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Download failed');
    } finally {
      setBusy(null);
    }
  }

  function canvasPath(s: SessionItem): string {
    const opts = getOpts(s);
    const columnTitle = opts.assignmentId.trim() ? `${opts.title} (${opts.assignmentId.trim()})` : opts.title;
    const params = new URLSearchParams({
      format: 'canvas',
      sis_domain: opts.sisDomain,
      roster_only: String(opts.rosterOnly),
      per_question: String(opts.perQuestion),
    });
    if (columnTitle) params.set('title', columnTitle);
    return `/sessions/${s.session_id}/export?${params}`;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-fg">Past Sessions</h2>

      {error && <p className="text-danger-text text-sm">{error}</p>}

      {loading ? (
        <p className="text-fg-muted">Loading…</p>
      ) : sessions.length === 0 ? (
        <p className="text-fg-muted">No finished sessions yet. Sessions appear here once a game ends.</p>
      ) : (
        <div className="space-y-2">
          {sessions.map((s) => {
            const opts = getOpts(s);
            const canvasOpen = canvasOpenId === s.session_id;
            return (
              <Card key={s.session_id} className="overflow-hidden">
                <div className="flex items-center gap-4 px-5 py-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-fg">{s.game_title}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                        s.status === 'COMPLETED' ? 'bg-accent-subtle text-accent-text' : 'bg-danger-subtle text-danger-text'
                      }`}>
                        {s.status === 'COMPLETED' ? 'Completed' : 'Abandoned'}
                      </span>
                    </div>
                    <p className="text-fg-subtle text-xs mt-0.5">
                      Room <span className="font-mono text-fg-muted">{s.room_code}</span>
                      {' · '}{s.player_count} player{s.player_count !== 1 ? 's' : ''}
                      {' · '}{fmtDate(s.created_at)}
                      {s.host_display_name && <span> · hosted by {s.host_display_name}</span>}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy === `${s.session_id}:report`}
                      onClick={() => void download(`${s.session_id}:report`, `/sessions/${s.session_id}/report`)}
                      title="Download an HTML summary of the questions and results"
                    >
                      <FileText size={13} className="mr-1" />
                      {busy === `${s.session_id}:report` ? 'Building…' : 'Summary (HTML)'}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy === `${s.session_id}:raw`}
                      onClick={() => void download(`${s.session_id}:raw`, `/sessions/${s.session_id}/export?format=raw`)}
                      title="Download per-player scores"
                    >
                      <Download size={13} className="mr-1" />
                      {busy === `${s.session_id}:raw` ? 'Downloading…' : 'Scores (CSV)'}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setCanvasOpenId(canvasOpen ? null : s.session_id)}
                    >
                      Canvas CSV
                      {canvasOpen ? <ChevronUp size={12} className="ml-1" /> : <ChevronDown size={12} className="ml-1" />}
                    </Button>
                  </div>
                </div>

                {canvasOpen && (
                  <div className="border-t border-line bg-surface px-5 py-4 space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs text-fg-muted mb-1">Assignment name</label>
                        <Input
                          value={opts.title}
                          onChange={(e) => setOpt(s, 'title', e.target.value)}
                          placeholder="Quiz title…"
                          className="text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-fg-muted mb-1">
                          Canvas assignment ID <span className="text-fg-subtle">(optional)</span>
                        </label>
                        <Input
                          value={opts.assignmentId}
                          onChange={(e) => setOpt(s, 'assignmentId', e.target.value)}
                          placeholder="e.g. 12345"
                          className="text-sm font-mono"
                        />
                      </div>
                    </div>
                    <div className="max-w-xs">
                      <label className="block text-xs text-fg-muted mb-1">
                        SIS Login ID domain <span className="text-fg-subtle">(appended to netid)</span>
                      </label>
                      <Input
                        value={opts.sisDomain}
                        onChange={(e) => setOpt(s, 'sisDomain', e.target.value)}
                        placeholder="wisc.edu"
                        className="text-sm font-mono"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="flex items-center gap-2 cursor-pointer select-none">
                        <input
                          type="checkbox"
                          checked={opts.rosterOnly}
                          onChange={(e) => setOpt(s, 'rosterOnly', e.target.checked)}
                          className="rounded border-line-strong accent-accent focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page"
                        />
                        <span className="text-sm text-fg-muted">
                          Roster-matched players only
                          <span className="text-fg-subtle ml-1 text-xs">(skip guests and local accounts without a netid)</span>
                        </span>
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer select-none">
                        <input
                          type="checkbox"
                          checked={opts.perQuestion}
                          onChange={(e) => setOpt(s, 'perQuestion', e.target.checked)}
                          className="rounded border-line-strong accent-accent focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page"
                        />
                        <span className="text-sm text-fg-muted">
                          Per-question breakdown
                          <span className="text-fg-subtle ml-1 text-xs">(one column per question, otherwise total only)</span>
                        </span>
                      </label>
                    </div>
                    <Button
                      size="sm"
                      disabled={busy === `${s.session_id}:canvas`}
                      onClick={() => void download(`${s.session_id}:canvas`, canvasPath(s))}
                    >
                      <Download size={13} className="mr-1.5" />
                      {busy === `${s.session_id}:canvas` ? 'Downloading…' : 'Download Canvas CSV'}
                    </Button>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
