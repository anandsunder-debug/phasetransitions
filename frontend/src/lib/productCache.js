import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const cache = new Map();

export function getCachedProduct(id) {
  return cache.get(id) || null;
}

export function prefetchProduct(id) {
  if (cache.has(id)) return;
  // Mark as loading to avoid duplicate fetches
  cache.set(id, null);
  axios.get(`${API}/products/${id}`).then(({ data }) => {
    cache.set(id, data);
  }).catch(() => {
    cache.delete(id);
  });
}
