export type PaintProject = {
  name: string;
  remessas: string[];
  retornos: string[];
  remittanceDayCount: number;
  totalSent?: number;
  totalReturned?: number;
  firstReturnDays?: number;
  conclusionDays?: number;
  status: "Concluído" | "Parcial" | "Sem retorno";
};

// Estrutura equivalente aos registros esperados do Formulário MTECH — Pintura.
// Na próxima etapa, esta lista será substituída pela leitura automática da
// planilha de respostas, sem alterar os cálculos ou o layout do painel.
export const timelineDates = [
  "13/07", "14/07", "15/07", "16/07", "17/07", "18/07", "19/07", "20/07", "21/07",
  "22/07", "23/07", "24/07", "25/07", "26/07", "27/07", "28/07", "29/07", "30/07",
];

export const paintProjects: PaintProject[] = [
  {
    name: "JDE ARAMADO G PILÃO VERMELHO 406+70",
    remessas: ["13/07", "14/07", "15/07", "16/07", "17/07"],
    retornos: ["20/07", "21/07", "22/07", "23/07", "24/07", "25/07", "27/07"],
    remittanceDayCount: 5,
    firstReturnDays: 7,
    conclusionDays: 14,
    status: "Concluído",
  },
  {
    name: "JDE ARAMADO G MARATÁ 261",
    remessas: ["18/07", "20/07"],
    retornos: ["21/07", "22/07", "27/07", "28/07", "29/07", "30/07"],
    remittanceDayCount: 3,
    firstReturnDays: 4,
    conclusionDays: 13,
    status: "Concluído",
  },
  {
    name: "JDE ARAMADO G PELE 85",
    remessas: ["20/07", "21/07"],
    retornos: ["29/07", "30/07"],
    remittanceDayCount: 2,
    firstReturnDays: 9,
    conclusionDays: 10,
    status: "Concluído",
  },
  {
    name: "JDE ARAMADO G DAMASCO 54",
    remessas: ["20/07", "21/07"],
    retornos: ["28/07", "29/07"],
    remittanceDayCount: 2,
    firstReturnDays: 8,
    conclusionDays: 9,
    status: "Concluído",
  },
  {
    name: "JDE ARAMADO G LOR 322",
    remessas: ["20/07", "22/07", "23/07", "24/07"],
    retornos: [],
    remittanceDayCount: 4,
    status: "Sem retorno",
  },
  {
    name: "JDE ARAMADO P PILÃO 211",
    remessas: ["24/07", "25/07", "28/07"],
    retornos: ["27/07", "30/07"],
    remittanceDayCount: 3,
    firstReturnDays: 3,
    conclusionDays: 6,
    status: "Parcial",
  },
  {
    name: "JDE ARAMADO P LOR 185",
    remessas: ["28/07"],
    retornos: [],
    remittanceDayCount: 1,
    status: "Sem retorno",
  },
  {
    name: "JDE ARAMADO P MARATÁ 40",
    remessas: ["28/07"],
    retornos: ["30/07"],
    remittanceDayCount: 1,
    firstReturnDays: 2,
    conclusionDays: 2,
    status: "Concluído",
  },
];
