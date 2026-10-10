import type { OpportunityStage } from '../data/opportunities';

export const OPPORTUNITY_STAGES: Array<{ key: OpportunityStage; label: string }> = [
  { key: 'new', label: 'Yeni fırsat' }, { key: 'contact', label: 'Temas' },
  { key: 'discovery', label: 'Keşif' }, { key: 'proposal', label: 'Teklif' },
  { key: 'decision', label: 'Karar' }, { key: 'won', label: 'Kazanıldı' }, { key: 'lost', label: 'Kaybedildi' },
];
export const stageLabel = (stage: OpportunityStage) => OPPORTUNITY_STAGES.find(item => item.key === stage)?.label || stage;
export const stageRank = (stage: OpportunityStage) => OPPORTUNITY_STAGES.findIndex(item => item.key === stage);
export const opportunityMoney = (value: number) => Number(value).toLocaleString('tr-TR', { style: 'currency', currency: 'TRY', maximumFractionDigits: 2 });
export const opportunityDate = (value: string) => new Date(value).toLocaleString('tr-TR', { timeZone: 'Europe/Istanbul', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
