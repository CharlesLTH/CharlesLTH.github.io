import { prepareIndex, queryIndex } from './search-core.mjs';
let index;
let ready;
self.onmessage = async ({ data }) => {
  try {
    if (!ready) ready = fetch('./browse-index.json').then(response => {
      if (!response.ok) throw new Error('索引读取失败');
      return response.json();
    }).then(document => { index = prepareIndex(document.items); return document.dataset_revision; }).catch(error => { ready = undefined; throw error; });
    const revision = await ready;
    self.postMessage({ id: data.id, result: { ...queryIndex(index, data.query), revision } });
  } catch (error) { self.postMessage({ id: data.id, error: error.message }); }
};
