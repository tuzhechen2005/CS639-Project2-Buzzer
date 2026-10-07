import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import QuestionEditorPage from './course/QuestionEditorPage';

/**
 * Question authoring for one game, reached from the Courses page. It is the same editor the
 * host app uses (an admin passes every course check there), so all six question types,
 * including numeric_estimate and plot_point, can be created and edited from the admin app.
 */
export default function GameQuestionsPage() {
  return (
    <div>
      <div className="px-8 pt-6">
        <Link
          to="/courses"
          className="inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-fg focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page rounded"
        >
          <ArrowLeft size={14} /> Courses
        </Link>
      </div>
      <QuestionEditorPage />
    </div>
  );
}
