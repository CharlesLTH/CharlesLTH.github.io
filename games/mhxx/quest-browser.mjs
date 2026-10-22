import { esc, route } from './ui.mjs';

export const questHubs = { village: '村任务', guild: '集会所', permit: '特殊许可', arena: '斗技大会', challenge: '挑战', event: '活动任务' };
export const questFlags = { key: '关键任务', urgent: '紧急任务', progression: '关键＋紧急' };
const questTypes = ['狩猎', '捕获', '讨伐', '采集', '连续狩猎', '猎猫', '特殊'];
const progressionGroups = new Set(['quest-2859', 'quest-2987']);

export function questGroupHub(group) {
  const label = group?.label || '';
  if (/^村/.test(label)) return 'village';
  if (/^(集|G\d)/.test(label)) return 'guild';
  if (/^特/.test(label)) return 'permit';
  if (/^斗技/.test(label)) return 'arena';
  if (/^挑战/.test(label)) return 'challenge';
  if (/^活动/.test(label)) return 'event';
  return '';
}

export function questFilterState(r, navigation) {
  const group = navigation.categories[r.group];
  return {
    hub: group ? questGroupHub(group) : Object.hasOwn(questHubs, r.qhub) ? r.qhub : '',
    flag: Object.hasOwn(questFlags, r.qflag) ? r.qflag : progressionGroups.has(r.group) ? 'progression' : '',
    type: questTypes.includes(r.qtype) ? r.qtype : '',
  };
}

export function renderQuestFilters(r, navigation) {
  const state = questFilterState(r, navigation);
  const base = { ...r, kind: 'quest', qhub: state.hub, qflag: state.flag, qtype: state.type, page: '' };
  const chip = (label, active, values) => `<a class="filter-chip ${active ? 'active' : ''}" href="${route({ ...base, ...values })}" ${active ? 'aria-current="true"' : ''}>${esc(label)}</a>`;
  const groups = navigation.sections['任务'].links.filter(link => link.route?.group && !progressionGroups.has(link.route.group));
  const groupOptions = Object.entries(questHubs).filter(([hub]) => !state.hub || state.hub === hub).map(([hub, title]) => {
    const options = groups.filter(link => questGroupHub(navigation.categories[link.route.group]) === hub);
    return options.length ? `<optgroup label="${title}">${options.map(link => {
      const label = link.label.replace(/^村(\d+)$/, '村 ★$1').replace(/^集(\d+)$/, '集会所 ★$1').replace(/^G(\d+)$/, 'G ★$1');
      return `<option value="${esc(link.route.group)}" ${r.group === link.route.group ? 'selected' : ''}>${esc(label)}</option>`;
    }).join('')}</optgroup>` : '';
  }).join('');
  return `<section class="panel quest-filters" aria-label="任务筛选">
    <div class="quest-filter-row"><span class="quest-filter-label">分类</span><nav class="filter-chips" aria-label="任务分类">${chip('全部', !state.hub, { qhub: '', group: '' })}${Object.entries(questHubs).map(([hub, label]) => chip(label, state.hub === hub, { qhub: hub, group: '' })).join('')}</nav></div>
    <div class="quest-filter-row"><span class="quest-filter-label">进度</span><nav class="filter-chips" aria-label="任务进度">${[['', '全部'], ...Object.entries(questFlags)].map(([flag, label]) => chip(label, state.flag === flag, { qflag: flag, group: progressionGroups.has(r.group) ? '' : r.group })).join('')}</nav></div>
    <div class="quest-filter-controls"><label>星级 / 难度<select class="select" data-route-select="group" data-quest-group aria-label="任务星级与难度"><option value="">全部星级 / 难度</option>${groupOptions}</select></label><label>任务类型<select class="select" data-route-select="qtype" aria-label="任务类型"><option value="">全部类型</option>${questTypes.map(type => `<option value="${type}" ${state.type === type ? 'selected' : ''}>${type}</option>`).join('')}</select></label></div>
  </section>`;
}
