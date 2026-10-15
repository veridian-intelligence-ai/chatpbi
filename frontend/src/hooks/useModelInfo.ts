import { useQuery } from '@tanstack/react-query';
import { fetchModelInfo, type ModelInfo } from '@/lib/api';

export const DEFAULT_MODEL_INFO: ModelInfo = {
  name: '',
  description: '',
  subject: '',
  currency: 'BRL',
  source: 'Power BI',
};

/**
 * Nome, assunto e moeda do modelo semântico ativo no backend (GET /model).
 * Trocar o modelo no backend (SEMANTIC_MODEL) muda o que a tela mostra sem
 * novo build do frontend.
 */
export function useModelInfo(): ModelInfo {
  const { data } = useQuery({
    queryKey: ['model-info'],
    queryFn: fetchModelInfo,
    staleTime: Infinity,
    retry: 1,
  });
  return data ?? DEFAULT_MODEL_INFO;
}
