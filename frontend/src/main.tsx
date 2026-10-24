import { render } from 'preact';
import { SessionBadge } from './visitor/SessionBadge';
import './boot';
import './app';

const host = document.getElementById('session-badge');
if (host) render(<SessionBadge />, host);
