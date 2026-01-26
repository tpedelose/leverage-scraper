--
-- PostgreSQL database dump
--

\restrict VBGp1MRlZrp92UxFJj0hrHCCZxlvR8KczhTd2pYnde5G1CC8VKLvJnZLEqMjS7P

-- Dumped from database version 18.1 (Debian 18.1-1.pgdg13+2)
-- Dumped by pg_dump version 18.0

-- Started on 2026-01-25 23:14:19

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
-- TOC entry 5 (class 2615 OID 2200)
-- Name: public; Type: SCHEMA; Schema: -; Owner: postgres
--

-- *not* creating schema, since initdb creates it


ALTER SCHEMA public OWNER TO postgres;

--
-- TOC entry 860 (class 1247 OID 16386)
-- Name: update_source_type; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.update_source_type AS ENUM (
    'manual',
    'scrape'
);


ALTER TYPE public.update_source_type OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 219 (class 1259 OID 16391)
-- Name: apartment_units; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.apartment_units (
    unit_id bigint NOT NULL,
    property_id bigint NOT NULL,
    floorplan_id bigint NOT NULL,
    unit_number character varying(20) NOT NULL,
    floor_number integer,
    building_name character varying(20),
    is_on_top_floor boolean,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.apartment_units OWNER TO postgres;

--
-- TOC entry 220 (class 1259 OID 16400)
-- Name: floorplans; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.floorplans (
    floorplan_id bigint NOT NULL,
    property_id integer NOT NULL,
    plan_name character varying(100) NOT NULL,
    bedrooms numeric(2,1) NOT NULL,
    bathrooms numeric(2,1) NOT NULL,
    square_footage integer,
    external_floorplan_id character varying,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.floorplans OWNER TO postgres;

--
-- TOC entry 221 (class 1259 OID 16412)
-- Name: floor_plans_floor_plan_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.floorplans ALTER COLUMN floorplan_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.floor_plans_floor_plan_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 222 (class 1259 OID 16413)
-- Name: management_companies; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.management_companies (
    company_id integer NOT NULL,
    name character varying(255) NOT NULL,
    website character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE public.management_companies OWNER TO postgres;

--
-- TOC entry 223 (class 1259 OID 16425)
-- Name: management_companies_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.management_companies ALTER COLUMN company_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.management_companies_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 224 (class 1259 OID 16426)
-- Name: price_history; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.price_history (
    scraped_at timestamp with time zone NOT NULL,
    unit_id bigint NOT NULL,
    rent_usd numeric(8,2) NOT NULL,
    deposit_usd numeric(8,2),
    min_lease_term_months smallint,
    is_available boolean,
    available_date date
);


ALTER TABLE public.price_history OWNER TO postgres;

--
-- TOC entry 225 (class 1259 OID 16432)
-- Name: properties; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.properties (
    property_id bigint NOT NULL,
    property_name character varying(255) NOT NULL,
    city character varying(50) NOT NULL,
    state character(2) NOT NULL,
    url text NOT NULL,
    template_engine character varying(50) NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    address text,
    postal_code character varying(10),
    company_id integer,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_source public.update_source_type DEFAULT 'manual'::public.update_source_type NOT NULL
);


ALTER TABLE public.properties OWNER TO postgres;

--
-- TOC entry 226 (class 1259 OID 16448)
-- Name: properties_property_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.properties ALTER COLUMN property_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.properties_property_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 227 (class 1259 OID 16449)
-- Name: units_unit_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.apartment_units ALTER COLUMN unit_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.units_unit_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 3325 (class 2606 OID 16451)
-- Name: floorplans floor_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.floorplans
    ADD CONSTRAINT floor_plans_pkey PRIMARY KEY (floorplan_id);


--
-- TOC entry 3327 (class 2606 OID 16453)
-- Name: floorplans floorplans_property_id_external_id; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.floorplans
    ADD CONSTRAINT floorplans_property_id_external_id UNIQUE (property_id, external_floorplan_id);


--
-- TOC entry 3329 (class 2606 OID 16455)
-- Name: floorplans floorplans_property_id_plan_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.floorplans
    ADD CONSTRAINT floorplans_property_id_plan_name_key UNIQUE (property_id, plan_name);


--
-- TOC entry 3331 (class 2606 OID 16457)
-- Name: management_companies management_companies_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.management_companies
    ADD CONSTRAINT management_companies_pkey PRIMARY KEY (company_id);


--
-- TOC entry 3333 (class 2606 OID 16459)
-- Name: management_companies management_companies_website_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.management_companies
    ADD CONSTRAINT management_companies_website_key UNIQUE (website);


--
-- TOC entry 3335 (class 2606 OID 16461)
-- Name: price_history price_history_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.price_history
    ADD CONSTRAINT price_history_pkey PRIMARY KEY (scraped_at, unit_id);


--
-- TOC entry 3337 (class 2606 OID 16463)
-- Name: properties properties_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.properties
    ADD CONSTRAINT properties_pkey PRIMARY KEY (property_id);


--
-- TOC entry 3339 (class 2606 OID 16465)
-- Name: properties properties_url_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.properties
    ADD CONSTRAINT properties_url_key UNIQUE (url);


--
-- TOC entry 3321 (class 2606 OID 16467)
-- Name: apartment_units units_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.apartment_units
    ADD CONSTRAINT units_pkey PRIMARY KEY (unit_id);


--
-- TOC entry 3323 (class 2606 OID 16469)
-- Name: apartment_units units_property_id_building_name_unit_number_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.apartment_units
    ADD CONSTRAINT units_property_id_building_name_unit_number_key UNIQUE (property_id, building_name, unit_number);


--
-- TOC entry 3344 (class 2606 OID 16470)
-- Name: properties fk_company; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.properties
    ADD CONSTRAINT fk_company FOREIGN KEY (company_id) REFERENCES public.management_companies(company_id) ON DELETE SET NULL;


--
-- TOC entry 3342 (class 2606 OID 16475)
-- Name: floorplans floorplans_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.floorplans
    ADD CONSTRAINT floorplans_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(property_id);


--
-- TOC entry 3343 (class 2606 OID 16480)
-- Name: price_history price_history_unit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.price_history
    ADD CONSTRAINT price_history_unit_id_fkey FOREIGN KEY (unit_id) REFERENCES public.apartment_units(unit_id);


--
-- TOC entry 3340 (class 2606 OID 16485)
-- Name: apartment_units units_floor_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.apartment_units
    ADD CONSTRAINT units_floor_plan_id_fkey FOREIGN KEY (floorplan_id) REFERENCES public.floorplans(floorplan_id);


--
-- TOC entry 3341 (class 2606 OID 16490)
-- Name: apartment_units units_property_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.apartment_units
    ADD CONSTRAINT units_property_id_fkey FOREIGN KEY (property_id) REFERENCES public.properties(property_id);


--
-- TOC entry 3497 (class 0 OID 0)
-- Dependencies: 5
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: postgres
--

REVOKE USAGE ON SCHEMA public FROM PUBLIC;
GRANT ALL ON SCHEMA public TO PUBLIC;
GRANT USAGE ON SCHEMA public TO scraper;


--
-- TOC entry 3498 (class 0 OID 0)
-- Dependencies: 219
-- Name: TABLE apartment_units; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,UPDATE ON TABLE public.apartment_units TO scraper;


--
-- TOC entry 3499 (class 0 OID 0)
-- Dependencies: 220
-- Name: TABLE floorplans; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,UPDATE ON TABLE public.floorplans TO scraper;


--
-- TOC entry 3500 (class 0 OID 0)
-- Dependencies: 221
-- Name: SEQUENCE floor_plans_floor_plan_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,USAGE ON SEQUENCE public.floor_plans_floor_plan_id_seq TO scraper;


--
-- TOC entry 3501 (class 0 OID 0)
-- Dependencies: 222
-- Name: TABLE management_companies; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.management_companies TO scraper;


--
-- TOC entry 3502 (class 0 OID 0)
-- Dependencies: 223
-- Name: SEQUENCE management_companies_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,USAGE ON SEQUENCE public.management_companies_id_seq TO scraper;


--
-- TOC entry 3503 (class 0 OID 0)
-- Dependencies: 224
-- Name: TABLE price_history; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,UPDATE ON TABLE public.price_history TO scraper;


--
-- TOC entry 3504 (class 0 OID 0)
-- Dependencies: 225
-- Name: TABLE properties; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,INSERT,UPDATE ON TABLE public.properties TO scraper;


--
-- TOC entry 3505 (class 0 OID 0)
-- Dependencies: 226
-- Name: SEQUENCE properties_property_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,USAGE ON SEQUENCE public.properties_property_id_seq TO scraper;


--
-- TOC entry 3506 (class 0 OID 0)
-- Dependencies: 227
-- Name: SEQUENCE units_unit_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,USAGE ON SEQUENCE public.units_unit_id_seq TO scraper;


-- Completed on 2026-01-25 23:14:19

--
-- PostgreSQL database dump complete
--

\unrestrict VBGp1MRlZrp92UxFJj0hrHCCZxlvR8KczhTd2pYnde5G1CC8VKLvJnZLEqMjS7P

