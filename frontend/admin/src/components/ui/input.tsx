import { cn } from '../../lib/utils';

type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

export function Input({ className, ...props }: InputProps) {
  return (
    <input
      className={cn(
        'w-full rounded-xl border border-line-strong bg-surface-raised px-3 py-2',
        'text-fg placeholder:text-fg-subtle',
        'focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        className
      )}
      {...props}
    />
  );
}
