import { apiFetch } from './api' // ajuste o caminho se o seu api.js estiver em outra pasta

export const getMap = () => apiFetch('/api/map')
export const getRoute = (start, end) =>
  apiFetch(`/api/route?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`)