import { QRCodeSVG } from 'qrcode.react';
import { Users } from 'lucide-react';
import { useGame } from './GameLayout';
import { Button } from '../../components/ui/button';

export default function LobbyPage() {
  const { roomCode, gameTitle, playerCount, emitAdvance, autoAdvance, setAutoAdvance } = useGame();

  const playerJoinUrl = `${window.location.origin}/player/join?code=${roomCode}`;

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-8 gap-8">
      {/* Quiz name */}
      {gameTitle && (
        <h1 className="text-3xl font-bold text-fg text-center">{gameTitle}</h1>
      )}

      {/* Join instructions */}
      <p className="text-fg-muted text-xl uppercase tracking-widest">
        Scan QR code or go to <span className="text-fg">{window.location.host}/player</span>
      </p>

      {/* QR code + room code side by side */}
      <div className="flex items-center gap-10">
        <div className="bg-qr rounded-2xl p-4">
          <QRCodeSVG value={playerJoinUrl} size={200} />
        </div>

        <div className="text-center">
          <p className="text-fg-muted text-base uppercase tracking-widest mb-2">Room Code</p>
          <div className="bg-surface border-2 border-accent rounded-2xl px-10 py-5 inline-block">
            <p className="text-8xl font-black tracking-widest text-fg font-mono">{roomCode}</p>
          </div>
        </div>
      </div>

      {/* Player count */}
      <div className="flex items-center gap-3 text-fg-muted text-xl">
        <Users className="w-6 h-6 text-accent-text" />
        <span>
          {playerCount === 0
            ? 'Waiting for players to join…'
            : `${playerCount} player${playerCount !== 1 ? 's' : ''} joined`}
        </span>
      </div>

      {/* Auto-advance toggle */}
      <button
        type="button"
        role="switch"
        aria-checked={autoAdvance}
        className="flex items-center gap-3 group focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page"
        onClick={() => setAutoAdvance(!autoAdvance)}
      >
        <div className={`w-12 h-6 rounded-full transition-colors relative ${autoAdvance ? 'bg-accent' : 'bg-line-strong'}`}>
          <div className={`absolute top-1 w-4 h-4 rounded-full bg-surface shadow transition-transform ${autoAdvance ? 'translate-x-7' : 'translate-x-1'}`} />
        </div>
        <span className="text-fg-muted text-xl group-hover:text-fg transition-colors select-none">
          Auto-advance — run game hands-free
        </span>
      </button>

      {/* Start button */}
      <Button size="lg" onClick={emitAdvance} disabled={playerCount === 0} className="px-12">
        {playerCount === 0 ? 'Waiting for players…' : 'Start Game'}
      </Button>
    </div>
  );
}
