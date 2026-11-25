ALTER TABLE public.painting_entries
  ADD COLUMN fornecedor_pintura text
    CONSTRAINT painting_entries_fornecedor_pintura_check
    CHECK (fornecedor_pintura IN ('Multipint', 'SCHUNCK', 'Aquapint'));
