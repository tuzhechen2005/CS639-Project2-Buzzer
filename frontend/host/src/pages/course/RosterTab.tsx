import { useEffect, useRef, useState } from 'react';
import { Upload, X, Pencil } from 'lucide-react';
import { api } from '../../lib/api';
import { Button } from '../../components/ui/button';
import { Card, CardContent, CardHeader } from '../../components/ui/card';
import { Input } from '../../components/ui/input';
import { useCourse } from './CourseLayout';

interface RosterEntry {
  id: number;
  netid: string;
  full_name: string;
  email: string;
  is_active: boolean;
  imported_at: string;
}

interface UploadResult {
  imported: number;
  updated: number;
  deactivated: number;
  errors: string[];
}

interface MappedRow {
  netid: string;
  full_name: string;
  email: string;
}

/** add_only upserts and deactivates nobody; replace also deactivates entries missing from the file. */
type ImportMode = 'add_only' | 'replace';

interface EditDraft {
  netid: string;
  full_name: string;
  email: string;
  is_active: boolean;
}

// ── Minimal RFC-4180-compliant CSV parser ─────────────────────────────────────
function parseCSV(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let inQuotes = false;
  let i = 0;
  while (i < text.length) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') { field += '"'; i += 2; continue; }
        inQuotes = false;
      } else {
        field += ch;
      }
    } else {
      if (ch === '"') { inQuotes = true; }
      else if (ch === ',') { row.push(field); field = ''; }
      else if (ch === '\n' || ch === '\r') {
        row.push(field); field = '';
        if (row.some((f) => f.trim() !== '')) rows.push(row);
        row = [];
        if (ch === '\r' && text[i + 1] === '\n') i++;
      } else { field += ch; }
    }
    i++;
  }
  if (field !== '' || row.length > 0) {
    row.push(field);
    if (row.some((f) => f.trim() !== '')) rows.push(row);
  }
  return rows;
}

// ── Apply column mapping + transforms to one raw CSV row ─────────────────────
function mapRow(
  rawRow: string[],
  headers: string[],
  netidCol: string,
  nameCol: string,
  emailCol: string,
  skipBlank: boolean,
  stripDomain: boolean,
  reverseName: boolean,
): MappedRow | null {
  const get = (col: string): string => {
    const idx = headers.indexOf(col);
    return idx >= 0 ? (rawRow[idx] ?? '').trim() : '';
  };

  let netid = get(netidCol);
  let full_name = get(nameCol);
  let email = get(emailCol);

  // Strip @domain from netid (Canvas: "NETID@WISC.EDU" → "netid")
  // When netidCol === emailCol, use the full value as email before stripping
  if (stripDomain && netid.includes('@')) {
    if (!email || emailCol === netidCol) email = netid;
    netid = netid.split('@')[0];
  }

  // Extract given name from "Last, First [Middle]" format
  if (reverseName && full_name.includes(',')) {
    full_name = full_name.split(',').slice(1).join(',').trim();
  }

  // Normalize
  netid = netid.toLowerCase();
  email = email.toLowerCase();
  // Title-case each word
  full_name = full_name.replace(/\b\w/g, (c) => c.toUpperCase());

  if (skipBlank && (!netid || !full_name || !email)) return null;
  return { netid, full_name, email };
}

// ── Component ─────────────────────────────────────────────────────────────────
export default function RosterTab() {
  const courseId = useCourse().id;
  const fileRef = useRef<HTMLInputElement>(null);

  // Roster list
  const [entries, setEntries] = useState<RosterEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Inline edit
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState<EditDraft | null>(null);
  const [saving, setSaving] = useState(false);

  // Wizard state
  const [step, setStep] = useState<'idle' | 'mapping' | 'result'>('idle');
  const [fileName, setFileName] = useState('');
  const [headers, setHeaders] = useState<string[]>([]);
  const [rawRows, setRawRows] = useState<string[][]>([]);
  const [netidCol, setNetidCol] = useState('');
  const [nameCol, setNameCol] = useState('');
  const [emailCol, setEmailCol] = useState('');
  const [skipRow2, setSkipRow2] = useState(false);
  const [stripDomain, setStripDomain] = useState(false);
  const [reverseName, setReverseName] = useState(false);
  const [importing, setImporting] = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [mode, setMode] = useState<ImportMode>('add_only');
  // Dry-run counts for the current file, mapping and mode; cleared whenever any of them changes
  const [preview, setPreview] = useState<UploadResult | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [confirmReplace, setConfirmReplace] = useState(false);
  // Replace mode with skipped or rejected rows: those students count as "not in this file"
  const [confirmSkipped, setConfirmSkipped] = useState(false);
  // Bumped whenever the mapping or mode changes, so a dry run that was still in flight for
  // the old settings is ignored instead of showing (and unlocking Import with) stale counts
  const previewSeq = useRef(0);

  async function load() {
    try {
      const data = await api.get<RosterEntry[]>(`/courses/${courseId}/roster`);
      setEntries(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load roster');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [courseId]);

  // Any change to the mapping or mode invalidates the dry-run preview
  useEffect(() => {
    previewSeq.current += 1;
    setPreview(null);
    setConfirmReplace(false);
    setConfirmSkipped(false);
  }, [mode, netidCol, nameCol, emailCol, skipRow2, stripDomain, reverseName, rawRows]);

  // ── File selected: parse + auto-detect ───────────────────────────────────
  function handleFileSelect(file: File) {
    setError('');
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = (e.target?.result as string) ?? '';
      const all = parseCSV(text);
      if (all.length === 0) { setError('CSV file appears to be empty.'); return; }

      const hdrs = all[0];
      const data = all.slice(1);
      setFileName(file.name);
      setHeaders(hdrs);
      setRawRows(data);

      // Case-insensitive column finder
      const lower = hdrs.map((h) => h.trim().toLowerCase());
      const find = (...candidates: string[]): string => {
        for (const c of candidates) {
          const idx = lower.indexOf(c);
          if (idx >= 0) return hdrs[idx];
        }
        return '';
      };

      const isCanvas = lower.includes('sis login id');
      const detNetid = find('sis login id', 'netid', 'login id');
      const detName  = find('student', 'full_name', 'full name', 'name');
      const detEmail = find('email');

      setNetidCol(detNetid || hdrs[0] || '');
      setNameCol(detName  || hdrs[1] || '');
      // Canvas: email comes from same column as netid (full "netid@domain" value)
      setEmailCol(detEmail || (isCanvas ? detNetid : hdrs[2]) || '');
      setStripDomain(isCanvas && !!detNetid);
      setReverseName(isCanvas && !!detName);

      // Auto-detect skip row 2: Canvas "Points Possible" metadata row
      const firstDataRow = data[0] ?? [];
      setSkipRow2(firstDataRow.some((cell) =>
        cell.trim().toLowerCase().startsWith('points possible'),
      ));

      setStep('mapping');
    };
    reader.readAsText(file);
  }

  // ── Build mapped rows from current wizard config ──────────────────────────
  function getMappedRows(): MappedRow[] {
    const dataRows = skipRow2 ? rawRows.slice(1) : rawRows;
    const result: MappedRow[] = [];
    for (const row of dataRows) {
      const mapped = mapRow(row, headers, netidCol, nameCol, emailCol, true, stripDomain, reverseName);
      if (mapped) result.push(mapped);
    }
    return result;
  }

  // Data rows the mapping drops (a required field is empty). They are never sent, so in
  // Replace mode those students would be deactivated without any error from the server.
  // Numbered like the raw preview's data rows (parseCSV already drops blank lines).
  function getSkippedRows(): { row: number; text: string }[] {
    const first = skipRow2 ? 2 : 1;
    const dataRows = skipRow2 ? rawRows.slice(1) : rawRows;
    const skipped: { row: number; text: string }[] = [];
    dataRows.forEach((row, i) => {
      if (!mapRow(row, headers, netidCol, nameCol, emailCol, true, stripDomain, reverseName)) {
        skipped.push({ row: first + i, text: row.filter((c) => c.trim()).join(', ') });
      }
    });
    return skipped;
  }

  // ── Import: always a dry run first, then the real import ──────────────────
  function importPath(dryRun: boolean): string {
    return `/courses/${courseId}/roster/import?mode=${mode}&dry_run=${dryRun}`;
  }

  async function handlePreview() {
    const rows = getMappedRows();
    if (rows.length === 0) { setError('No valid rows to import with the current mapping.'); return; }
    const seq = previewSeq.current;
    setPreviewing(true);
    setError('');
    try {
      const result = await api.post<UploadResult>(importPath(true), { rows });
      if (seq !== previewSeq.current) return; // settings changed meanwhile; preview again
      setPreview(result);
      setConfirmReplace(false);
      setConfirmSkipped(false);
    } catch (err) {
      if (seq === previewSeq.current) setError(err instanceof Error ? err.message : 'Preview failed');
    } finally {
      setPreviewing(false);
    }
  }

  async function handleImport() {
    const rows = getMappedRows();
    if (rows.length === 0) { setError('No valid rows to import with the current mapping.'); return; }
    setImporting(true);
    setError('');
    try {
      const result = await api.post<UploadResult>(importPath(false), { rows });
      setUploadResult(result);
      setStep('result');
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed');
    } finally {
      setImporting(false);
    }
  }

  function resetWizard() {
    setStep('idle');
    setFileName('');
    setHeaders([]);
    setRawRows([]);
    setUploadResult(null);
    setMode('add_only');
    setPreview(null);
    setConfirmReplace(false);
    setConfirmSkipped(false);
    setError('');
    if (fileRef.current) fileRef.current.value = '';
  }

  // ── Inline edit ───────────────────────────────────────────────────────────
  function startEdit(entry: RosterEntry) {
    setEditingId(entry.id);
    setEditDraft({
      netid: entry.netid,
      full_name: entry.full_name,
      email: entry.email,
      is_active: entry.is_active,
    });
    setError('');
  }

  function cancelEdit() {
    setEditingId(null);
    setEditDraft(null);
  }

  async function saveEdit(entryId: number) {
    if (!editDraft) return;
    setSaving(true);
    setError('');
    try {
      const updated = await api.patch<RosterEntry>(
        `/courses/${courseId}/roster/${entryId}`,
        editDraft,
      );
      setEntries((prev) => prev.map((e) => e.id === entryId ? updated : e));
      setEditingId(null);
      setEditDraft(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Update failed');
    } finally {
      setSaving(false);
    }
  }

  // Compute once; only meaningful in mapping step
  const mappedRows = step === 'mapping' ? getMappedRows() : [];
  const previewRows = mappedRows.slice(0, 3);
  const totalRows = mappedRows.length;
  const skippedRows = step === 'mapping' ? getSkippedRows() : [];
  const replaceNeedsSkipConfirm =
    mode === 'replace' && preview !== null && (skippedRows.length > 0 || preview.errors.length > 0);

  const active = entries.filter((e) => e.is_active);
  const inactive = entries.filter((e) => !e.is_active);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold text-fg">Roster</h2>
        {step === 'idle' && (
          <>
            <input
              ref={fileRef}
              type="file"
              accept=".csv"
              className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFileSelect(f); }}
            />
            <Button size="sm" onClick={() => fileRef.current?.click()}>
              <Upload size={14} className="mr-1" /> Upload CSV
            </Button>
          </>
        )}
      </div>

      {error && <p className="text-danger-text mb-4 text-sm">{error}</p>}

      {/* ── Column-mapping wizard ── */}
      {step === 'mapping' && (
        <Card className="mb-6">
          <CardHeader>
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-fg">Map Columns — {fileName}</h3>
              <button onClick={resetWizard} className="text-fg-muted hover:text-fg"><X size={16} /></button>
            </div>
          </CardHeader>
          <CardContent className="space-y-5">

            {/* Raw CSV preview */}
            <div>
              <p className="text-xs text-fg-muted mb-2">
                Raw preview — {rawRows.length} data row{rawRows.length !== 1 ? 's' : ''} detected:
              </p>
              <div className="overflow-x-auto rounded border border-line">
                <table className="text-xs text-fg-muted w-full">
                  <thead>
                    <tr className="bg-surface-raised">
                      {headers.map((h, i) => (
                        <th key={i} className="px-3 py-2 text-left font-medium whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rawRows.slice(0, 4).map((row, ri) => (
                      <tr
                        key={ri}
                        className={`border-t border-line ${ri === 0 && skipRow2 ? 'opacity-30 line-through' : ''}`}
                      >
                        {headers.map((_, ci) => (
                          <td key={ci} className="px-3 py-1.5 max-w-[180px] truncate">{row[ci] ?? ''}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Column selectors */}
            <div className="grid grid-cols-3 gap-4">
              {([
                { label: 'NetID column', value: netidCol, set: setNetidCol },
                { label: 'Full name column', value: nameCol, set: setNameCol },
                { label: 'Email column', value: emailCol, set: setEmailCol },
              ] as const).map(({ label, value, set }) => (
                <div key={label}>
                  <label className="text-xs text-fg-muted block mb-1">{label}</label>
                  <select
                    value={value}
                    onChange={(e) => set(e.target.value)}
                    className="w-full bg-surface-raised border border-line-strong rounded px-2 py-1.5 text-sm text-fg focus-visible:outline-none focus-visible:ring-2 ring-focus ring-offset-2 ring-offset-page"
                  >
                    {headers.map((h) => <option key={h} value={h}>{h}</option>)}
                  </select>
                </div>
              ))}
            </div>

            {/* Options */}
            <div className="space-y-2">
              {([
                {
                  id: 'skip2',
                  checked: skipRow2,
                  set: setSkipRow2,
                  label: 'Skip row 2 — e.g. Canvas "Points Possible" metadata row',
                },
                {
                  id: 'strip',
                  checked: stripDomain,
                  set: setStripDomain,
                  label: 'Strip @domain from NetID column (netid@wisc.edu → netid; full address used as email)',
                },
                {
                  id: 'rev',
                  checked: reverseName,
                  set: setReverseName,
                  label: 'Name is in "Last, First" format — extract given name only',
                },
              ] as const).map(({ id, checked, set, label }) => (
                <label key={id} className="flex items-center gap-2 text-sm text-fg-muted cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(e) => set(e.target.checked)}
                    className="rounded border-line-strong bg-surface-raised accent-accent"
                  />
                  {label}
                </label>
              ))}
            </div>
            <p className="text-xs text-fg-subtle">Rows missing any required field after mapping are automatically skipped.</p>

            {/* Mapped preview */}
            {previewRows.length > 0 && (
              <div>
                <p className="text-xs text-fg-muted mb-2">
                  Mapped preview — {totalRows} row{totalRows !== 1 ? 's' : ''} will be imported:
                </p>
                <div className="rounded border border-line overflow-hidden">
                  <table className="text-xs text-fg-muted w-full">
                    <thead>
                      <tr className="bg-surface-raised">
                        <th className="px-3 py-2 text-left">netid</th>
                        <th className="px-3 py-2 text-left">full_name</th>
                        <th className="px-3 py-2 text-left">email</th>
                      </tr>
                    </thead>
                    <tbody>
                      {previewRows.map((r, i) => (
                        <tr key={i} className="border-t border-line">
                          <td className="px-3 py-1.5">{r.netid}</td>
                          <td className="px-3 py-1.5">{r.full_name}</td>
                          <td className="px-3 py-1.5">{r.email}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Import mode */}
            <div>
              <p className="text-xs text-fg-muted mb-2">Import mode</p>
              <div className="space-y-2">
                {([
                  {
                    value: 'add_only',
                    label: 'Add only',
                    hint: 'Add new students and update existing ones. Nobody is deactivated.',
                  },
                  {
                    value: 'replace',
                    label: 'Replace roster',
                    hint: 'Also deactivate every student who is not in this file.',
                  },
                ] as const).map((m) => (
                  <label key={m.value} className="flex items-start gap-2 text-sm text-fg-muted cursor-pointer select-none">
                    <input
                      type="radio"
                      name="roster-mode"
                      checked={mode === m.value}
                      onChange={() => setMode(m.value)}
                      disabled={previewing || importing}
                      className="mt-1 accent-accent"
                    />
                    <span>
                      <span className="font-medium text-fg">{m.label}</span>
                      <span className="block text-xs text-fg-subtle">{m.hint}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>

            {/* Dry-run counts */}
            {preview && (
              <div className="rounded border border-line bg-surface px-4 py-3 space-y-2">
                <p className="text-sm text-fg">
                  This import will add <strong>{preview.imported}</strong>, update{' '}
                  <strong>{preview.updated}</strong> and deactivate{' '}
                  <strong className={preview.deactivated > 0 ? 'text-danger-text' : ''}>{preview.deactivated}</strong>{' '}
                  student{preview.deactivated !== 1 ? 's' : ''}.
                </p>
                {preview.errors.length > 0 && (
                  <ul className="text-danger-text text-xs space-y-1">
                    {preview.errors.map((e, i) => <li key={i}>{e}</li>)}
                  </ul>
                )}
                {skippedRows.length > 0 && (
                  <div className="text-xs text-warning-text space-y-1">
                    <p>
                      {skippedRows.length} row{skippedRows.length !== 1 ? 's were' : ' was'} skipped
                      (missing netid, name or email) and won't be imported:
                    </p>
                    <ul className="space-y-0.5 text-warning-text">
                      {skippedRows.slice(0, 5).map((r) => <li key={r.row}>Data row {r.row}: {r.text}</li>)}
                      {skippedRows.length > 5 && <li>…and {skippedRows.length - 5} more</li>}
                    </ul>
                  </div>
                )}
                {replaceNeedsSkipConfirm && (
                  <label className="flex items-center gap-2 text-sm text-danger-text cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={confirmSkipped}
                      onChange={(e) => setConfirmSkipped(e.target.checked)}
                      className="rounded border-line-strong bg-surface-raised accent-danger"
                    />
                    I understand that students in the skipped or rejected rows count as not in this
                    file, so Replace will deactivate them if they are on the roster.
                  </label>
                )}
                {mode === 'replace' && preview.deactivated > 0 && (
                  <label className="flex items-center gap-2 text-sm text-danger-text cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={confirmReplace}
                      onChange={(e) => setConfirmReplace(e.target.checked)}
                      className="rounded border-line-strong bg-surface-raised accent-danger"
                    />
                    I understand that {preview.deactivated} student{preview.deactivated !== 1 ? 's' : ''} not
                    in this file will be deactivated and can no longer join this course's games.
                  </label>
                )}
              </div>
            )}

            <div className="flex gap-3">
              {preview ? (
                <Button
                  onClick={() => void handleImport()}
                  disabled={
                    importing || totalRows === 0
                    || (mode === 'replace' && preview.deactivated > 0 && !confirmReplace)
                    || (replaceNeedsSkipConfirm && !confirmSkipped)
                  }
                >
                  {importing ? 'Importing…' : `Import ${totalRows} row${totalRows !== 1 ? 's' : ''}`}
                </Button>
              ) : (
                <Button onClick={() => void handlePreview()} disabled={previewing || totalRows === 0}>
                  {previewing ? 'Checking…' : 'Preview import'}
                </Button>
              )}
              <Button variant="ghost" onClick={resetWizard}>Cancel</Button>
            </div>

          </CardContent>
        </Card>
      )}

      {/* ── Result banner ── */}
      {step === 'result' && uploadResult && (
        <Card className="mb-6 p-4 border-success bg-success-subtle">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-success-text text-sm font-medium">
                Import complete &mdash; {uploadResult.imported} imported, {uploadResult.updated} updated,{' '}
                {uploadResult.deactivated} deactivated
              </p>
              {uploadResult.errors.length > 0 && (
                <ul className="mt-2 text-danger-text text-xs space-y-1">
                  {uploadResult.errors.map((e, i) => <li key={i}>{e}</li>)}
                </ul>
              )}
            </div>
            <button onClick={resetWizard} className="text-fg-muted hover:text-fg ml-4"><X size={16} /></button>
          </div>
        </Card>
      )}

      {/* ── Roster table ── */}
      {loading ? (
        <p className="text-fg-muted">Loading…</p>
      ) : entries.length === 0 ? (
        <p className="text-fg-subtle text-sm">No roster entries yet. Upload a CSV to get started.</p>
      ) : (
        <>
          <p className="text-fg-muted text-sm mb-4">{active.length} active &middot; {inactive.length} inactive</p>
          <div className="rounded-xl border border-line overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-surface text-xs text-fg-muted border-b border-line">
                  <th className="text-left px-4 py-3 font-medium">Full Name</th>
                  <th className="text-left px-4 py-3 font-medium">NetID</th>
                  <th className="text-left px-4 py-3 font-medium">Email</th>
                  <th className="text-left px-4 py-3 font-medium">Status</th>
                  <th className="text-left px-4 py-3 font-medium">Imported</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) =>
                  editingId === entry.id && editDraft ? (
                    // ── Edit row ──
                    <tr key={entry.id} className="border-t border-line bg-surface-raised">
                      <td className="px-3 py-2">
                        <Input
                          value={editDraft.full_name}
                          onChange={(e) => setEditDraft({ ...editDraft, full_name: e.target.value })}
                          className="h-8 text-sm"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <Input
                          value={editDraft.netid}
                          onChange={(e) => setEditDraft({ ...editDraft, netid: e.target.value })}
                          className="h-8 text-sm font-mono"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <Input
                          value={editDraft.email}
                          onChange={(e) => setEditDraft({ ...editDraft, email: e.target.value })}
                          className="h-8 text-sm"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <label className="flex items-center gap-2 cursor-pointer select-none">
                          <input
                            type="checkbox"
                            checked={editDraft.is_active}
                            onChange={(e) => setEditDraft({ ...editDraft, is_active: e.target.checked })}
                            className="rounded border-line-strong bg-surface-raised accent-accent"
                          />
                          <span className="text-fg-muted text-xs">Active</span>
                        </label>
                      </td>
                      <td className="px-4 py-2 text-fg-subtle text-xs whitespace-nowrap">
                        {new Date(entry.imported_at).toLocaleDateString()}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex gap-2 justify-end">
                          <Button size="sm" onClick={() => void saveEdit(entry.id)} disabled={saving}>
                            {saving ? 'Saving…' : 'Save'}
                          </Button>
                          <Button variant="ghost" size="sm" onClick={cancelEdit} disabled={saving}>
                            Cancel
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ) : (
                    // ── View row ──
                    <tr
                      key={entry.id}
                      className={`border-t border-line hover:bg-surface-raised transition-colors ${
                        !entry.is_active ? 'opacity-50' : ''
                      }`}
                    >
                      <td className="px-4 py-3 font-medium text-fg">{entry.full_name}</td>
                      <td className="px-4 py-3 font-mono text-xs text-fg-muted">{entry.netid}</td>
                      <td className="px-4 py-3 text-fg-muted">{entry.email}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-block text-xs font-semibold px-2 py-0.5 rounded-full ${
                          entry.is_active
                            ? 'bg-success-subtle text-success-text'
                            : 'bg-surface-raised text-fg-muted'
                        }`}>
                          {entry.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-fg-subtle text-xs whitespace-nowrap">
                        {new Date(entry.imported_at).toLocaleDateString()}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => startEdit(entry)}
                        >
                          <Pencil size={12} className="mr-1" /> Edit
                        </Button>
                      </td>
                    </tr>
                  )
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
