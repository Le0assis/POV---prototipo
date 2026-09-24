// Provisório: o back-end ainda não guarda andar, sala e categoria.
// A chave é o nome do checkpoint (o mesmo "id" devolvido por /api/map).
const META = {
  'Sala 101': { categoria: 'Clínico', andar: 1, sala: '101', favorito: true },
  'Sala 102': { categoria: 'Clínico', andar: 1, sala: '102' },
  'Sala 103': { categoria: 'Clínico', andar: 1, sala: '103' },
  Escada: { categoria: 'Saídas', andar: 1 },
  Recepcao: { categoria: 'Saídas', andar: 1 },
}

export const CATEGORIAS = ['Favoritos', 'Clínico', 'Saídas']

export const placeMeta = (nome) => ({
  categoria: 'Clínico', andar: 1, sala: '-', favorito: false, ...META[nome],
})