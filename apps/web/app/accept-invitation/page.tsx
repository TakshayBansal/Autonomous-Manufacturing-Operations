'use client';

import { FormEvent, useEffect, useState } from 'react';
import Link from 'next/link';

import { apiFetch } from '@/lib/api';

export default function AcceptInvitationPage() {
  const [token, setToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [acceptedEmail, setAcceptedEmail] = useState('');

  useEffect(() => setToken(new URLSearchParams(window.location.search).get('token') ?? ''), []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError('');
    try {
      const result = await apiFetch<{ email: string }>('/workspace/invitations/accept', {
        method: 'POST',
        headers: { 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({ token, name: form.get('name'), password: form.get('password') }),
      });
      setAcceptedEmail(result.email);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Invitation could not be accepted');
    } finally {
      setBusy(false);
    }
  }

  return <main className='v2-auth-shell v2-invitation-shell'>
    <section className='v2-auth-card'>
      <div className='v2-auth-brand'><span className='v2-auth-wordmark'>G</span><div><strong>GenuineGigs</strong><small>Manufacturing Operations OS</small></div><b>V2</b></div>
      <div className='v2-auth-copy'><span>Workspace invitation</span>
      <h1>{acceptedEmail ? 'Your workspace access is ready' : 'Join your operating workspace'}</h1>
      <p>{acceptedEmail?'Your account has been added with its assigned operational role.':'Create your secure identity. Your plant and role access have already been assigned.'}</p></div>
      {acceptedEmail ? <Link className='v2-auth-primary-link' href={`/login?email=${encodeURIComponent(acceptedEmail)}`}>Sign in to workspace</Link> : <form onSubmit={submit}>
        <label>Full name<input name='name' autoComplete='name' required /></label>
        <label>Create password<input name='password' type='password' minLength={10} autoComplete='new-password' required /></label>
        <button disabled={busy || !token}>{busy ? 'Creating access…' : 'Accept invitation'}</button>
      </form>}
      {!token && !acceptedEmail && <div className='v2-auth-error'>This invitation link is missing its one-time token.</div>}
      {error && <div className='v2-auth-error'>{error}</div>}
    </section>
  </main>;
}
