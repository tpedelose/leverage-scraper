--
-- PostgreSQL database dump
--

\restrict 9gkAIgabse8CfUwGL9z6Iev7sD3ARbrVgcmTbCDEa7bPn4n2Vbape3gvFnkXtnf

-- Dumped from database version 18.1 (Debian 18.1-1.pgdg13+2)
-- Dumped by pg_dump version 18.0

-- Started on 2026-02-02 21:32:28

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- TOC entry 3458 (class 0 OID 16413)
-- Dependencies: 222
-- Data for Name: management_companies; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.management_companies (company_id, name, website, created_at, updated_at) FROM stdin;
1	Dolben	https://www.dolben.com/	2025-11-26 09:45:04.643719+00	2025-11-26 09:45:04.643719+00
2	UDR	https://www.udr.com/	2025-11-26 09:47:30.430875+00	2025-11-26 09:47:30.430875+00
\.


--
-- TOC entry 3467 (class 0 OID 0)
-- Dependencies: 223
-- Name: management_companies_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.management_companies_id_seq', 2, true);


-- Completed on 2026-02-02 21:32:28

--
-- PostgreSQL database dump complete
--

\unrestrict 9gkAIgabse8CfUwGL9z6Iev7sD3ARbrVgcmTbCDEa7bPn4n2Vbape3gvFnkXtnf

