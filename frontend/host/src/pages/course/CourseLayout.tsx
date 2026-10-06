import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useMatch, useOutletContext, useParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { api } from '../../lib/api';
import { ThemeToggle } from '../../components/ThemeToggle';

export interface Course { id: number; name: string; semester: string }

interface CourseContext { course: Course }

/** The course this page is nested under (only available inside CourseLayout). */
export function useCourse(): Course {
  return useOutletContext<CourseContext>().course;
}

/**
 * Course header plus Games / Roster / Past Sessions tabs. There is no single-course
 * endpoint, so the course is looked up in `my-courses`; a course the user doesn't
 * host (including the system course) shows a "no access" message and no tabs.
 */
export default function CourseLayout() {
  const { courseId } = useParams<{ courseId: string }>();
  const onEditor = useMatch('/courses/:courseId/games/:gameId/questions') !== null;
  const [course, setCourse] = useState<Course | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'no-access' | 'error'>('loading');
  const [error, setError] = useState('');

  useEffect(() => {
    setState('loading');
    api.get<Course[]>('/game/my-courses')
      .then((courses) => {
        const found = courses.find((c) => String(c.id) === courseId);
        setCourse(found ?? null);
        setState(found ? 'ready' : 'no-access');
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Failed to load course');
        setState('error');
      });
  }, [courseId]);

  const tabClass = ({ isActive }: { isActive: boolean }) =>
    `px-4 py-2 rounded-lg text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page ${
      isActive ? 'bg-accent text-on-accent' : 'text-fg-muted hover:text-fg'
    }`;

  if (state === 'loading') {
    return <div className="p-8 text-fg-muted">Loading…</div>;
  }

  if (state !== 'ready' || !course) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <ThemeToggle className="fixed top-4 right-4" />
        <div className="text-center space-y-4">
          <p className="text-fg-muted text-lg">
            {state === 'error' ? error : "You don't have access to this course."}
          </p>
          <Link to="/home" className="text-accent-text underline focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page">Back to your courses</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen p-6 md:p-8">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="space-y-3">
          <Link
            to={onEditor ? `/courses/${course.id}/games` : '/home'}
            className="inline-flex items-center gap-2 text-fg-muted hover:text-fg text-sm focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page"
          >
            <ArrowLeft size={14} /> {onEditor ? 'Back to Games' : 'All courses'}
          </Link>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-fg">{course.name}</h1>
              <p className="text-fg-muted text-sm">{course.semester}</p>
            </div>
            <ThemeToggle />
          </div>
          {!onEditor && (
            <nav className="inline-flex gap-1 bg-surface-raised rounded-xl p-1">
              <NavLink to="games" className={tabClass}>Games</NavLink>
              <NavLink to="roster" className={tabClass}>Roster</NavLink>
              <NavLink to="sessions" className={tabClass}>Past Sessions</NavLink>
            </nav>
          )}
        </div>
        <Outlet context={{ course } satisfies CourseContext} />
      </div>
    </div>
  );
}
