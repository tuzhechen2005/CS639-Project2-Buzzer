import { cn } from '../../lib/utils';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'outline' | 'ghost' | 'destructive';
  size?: 'sm' | 'md' | 'lg';
}

export function Button({ className, variant = 'default', size = 'md', ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center rounded-xl font-semibold transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        'min-h-11 enabled:active:scale-95',
        variant === 'default' && 'bg-accent text-on-accent enabled:hover:bg-accent-hover',
        variant === 'outline' && 'border border-line-strong text-fg enabled:hover:bg-surface-raised',
        variant === 'ghost' && 'text-fg-muted enabled:hover:bg-surface-raised enabled:hover:text-fg',
        variant === 'destructive' && 'bg-danger text-on-danger enabled:hover:[&:not(:active)]:brightness-95 active:brightness-90',
        size === 'sm' && 'px-3 py-2 text-sm',
        size === 'md' && 'px-5 py-3 text-base',
        size === 'lg' && 'px-6 py-4 text-lg',
        className
      )}
      {...props}
    />
  );
}
