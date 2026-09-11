'use client';

import Link from 'next/link';
import { Search, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

import type { WorkspaceOverview } from '@/lib/api';


export function WorkspaceCommandPalette({ overview }: { overview: WorkspaceOverview }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setOpen((value) => !value);
      }
      if (event.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', listener);
    return () => window.removeEventListener('keydown', listener);
  }, []);
  useEffect(() => {
    if (open) window.setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);
  const commands = useMemo(() => {
    const navigation = overview.nav_items.map((item) => ({
      id: item.href, label: item.label, detail: item.group === 'my_work' ? 'My work' : 'Process record',
      href: item.href,
    }));
    const tasks = overview.work_items.map((item) => ({
      id: item.id, label: item.title, detail: item.plain_language_goal, href: item.href,
    }));
    const needle = query.trim().toLowerCase();
    return [...navigation, ...tasks].filter((item) => !needle || (item.label + ' ' + item.detail).toLowerCase().includes(needle)).slice(0, 12);
  }, [overview, query]);
  return <>
    <button className='command-palette-trigger' type='button' onClick={() => setOpen(true)}><Search size={14} /> Search or go to <kbd>Ctrl K</kbd></button>
    {open && <div className='command-palette-backdrop' role='presentation' onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
      <section className='command-palette' role='dialog' aria-modal='true' aria-label='Workspace commands'>
        <header><Search size={17} /><input ref={inputRef} value={query} onChange={(event) => setQuery(event.target.value)} placeholder='Search navigation and assigned work' /><button type='button' onClick={() => setOpen(false)} aria-label='Close commands'><X size={17} /></button></header>
        <div>{commands.map((command) => <Link key={command.id} href={command.href} onClick={() => setOpen(false)}><strong>{command.label}</strong><span>{command.detail}</span></Link>)}</div>
        {!commands.length && <p>No matching authorized command.</p>}
      </section>
    </div>}
  </>;
}
