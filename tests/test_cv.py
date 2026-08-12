"""The CV document: strict parsing, one rendering, and the Person it states.

A CV is a record, so it is declared as data and rendered from there.  These
tests hold the two ends together: every fact the document declares reaches
the page, and the ``Person`` the page emits carries what a CV knows on top of
the site's declared author.
"""

import json
import os
import re

import pytest

from conftest import TEST_AUTHOR, default_config
from selfdoc_core.content import resolve_content
from selfdoc_core.cv import (
    CV_PAGE_TYPE,
    CV_PERSON_ATTR,
    cv_person_jsonld,
    extract_cv_person,
    load_cv,
    parse_cv,
    render_cv_markdown,
)

DOCUMENT = """
format_version = 1

[identity]
name = "Ada Lovelace"
headline = "Analyst"
location = "London, England"
email = "ada@example.org"
photo = "pic.jpg"
updated = "October 10th, 1852"
summary = "I write [notes](https://example.org/notes) about engines."

  [[identity.profile]]
  label = "example.org/ada"
  url = "https://example.org/ada"

[[skills]]
category = "Languages"
items = ["Analytical Engine notation", "French"]

[[skills]]
category = "Other"
items = ["Correspondence"]

[[projects]]
name = "Note G"
notes = ["The first published algorithm"]
technologies = ["Analytical Engine"]

[[projects]]
name = "Translation"
technologies = ["French"]

[[interests]]
title = "Poetical science"
body = "Imagination is the *discovering* faculty."

[[education]]
degree = "Private tuition in mathematics"
years = "1833 - 1840"
institute = "University of London"
institute_url = "https://london.example"
location = "London, England"
focus = "Mathematics"
thesis = "On the Analytical Engine"
course_url = "https://london.example/course"

[[experience]]
role = "Translator and analyst"
period = "1842 - 1843"
company = "Scientific Memoirs"
company_url = "https://memoirs.example"
location = "London, England"
body = "Translated Menabrea's memoir and appended notes three times its length."

[[experience]]
role = "Correspondent"
period = "1840"
company = "Self-employed"
location = "England"

[[languages]]
name = "English"
level = "Native"

[[languages]]
name = "French"
url = "https://example.org/french"
level = "Fluent"

[contact]
body = "Write to [ada@example.org](mailto:ada@example.org)."
"""


def _without(block_key):
    """Return DOCUMENT with one whole section removed."""
    lines = DOCUMENT.split("\n")
    out, skipping = [], False
    for line in lines:
        if line.startswith("[[") or (line.startswith("[") and not line.startswith("[[")):
            skipping = line.startswith(f"[[{block_key}]]") or line == f"[{block_key}]"
        if not skipping:
            out.append(line)
    return "\n".join(out)


# -- parsing ------------------------------------------------------------------


class TestParsing:
    def test_the_document_parses(self):
        cv = parse_cv(DOCUMENT)
        assert cv.identity.name == "Ada Lovelace"
        assert [g.category for g in cv.skills] == ["Languages", "Other"]
        assert [p.name for p in cv.projects] == ["Note G", "Translation"]
        assert len(cv.education) == 1
        assert len(cv.experience) == 2
        assert [lang.name for lang in cv.languages] == ["English", "French"]
        assert cv.contact.startswith("Write to")

    def test_a_wrong_format_version_is_refused(self):
        with pytest.raises(RuntimeError, match="format_version"):
            parse_cv(DOCUMENT.replace("format_version = 1", "format_version = 2"))

    def test_an_unknown_top_level_key_is_refused(self):
        with pytest.raises(RuntimeError, match="publications"):
            parse_cv(DOCUMENT + '\n[publications]\nbody = "none"\n')

    def test_an_unknown_identity_key_is_refused(self):
        with pytest.raises(RuntimeError, match="nickname"):
            parse_cv(DOCUMENT.replace(
                'name = "Ada Lovelace"', 'name = "Ada"\nnickname = "AAL"',
            ))

    def test_an_unknown_block_key_is_refused(self):
        with pytest.raises(RuntimeError, match="grade"):
            parse_cv(DOCUMENT.replace(
                'focus = "Mathematics"', 'focus = "Mathematics"\ngrade = "110"',
            ))

    @pytest.mark.parametrize("section", [
        "skills", "projects", "interests", "education", "experience",
        "languages",
    ])
    def test_an_absent_section_is_refused(self, section):
        with pytest.raises(RuntimeError, match=section):
            parse_cv(_without(section))

    def test_an_absent_identity_is_refused(self):
        with pytest.raises(RuntimeError, match="identity"):
            parse_cv(_without("identity"))

    def test_an_absent_contact_is_refused(self):
        with pytest.raises(RuntimeError, match="contact"):
            parse_cv(_without("contact"))

    def test_a_missing_required_field_is_refused(self):
        with pytest.raises(RuntimeError, match="'email'"):
            parse_cv(DOCUMENT.replace('email = "ada@example.org"\n', "", 1))

    def test_an_empty_required_field_is_refused(self):
        with pytest.raises(RuntimeError, match="'headline'"):
            parse_cv(DOCUMENT.replace('headline = "Analyst"', 'headline = "  "'))

    def test_a_repeated_skill_category_is_refused(self):
        with pytest.raises(RuntimeError, match="repeats"):
            parse_cv(DOCUMENT.replace(
                'category = "Other"', 'category = "Languages"',
            ))

    def test_a_repeated_project_is_refused(self):
        with pytest.raises(RuntimeError, match="repeats"):
            parse_cv(DOCUMENT.replace('name = "Translation"', 'name = "Note G"'))

    def test_a_project_with_nothing_to_say_is_refused(self):
        with pytest.raises(RuntimeError, match="bare heading"):
            parse_cv(DOCUMENT.replace(
                'name = "Translation"\ntechnologies = ["French"]',
                'name = "Translation"',
            ))

    def test_malformed_toml_names_the_source(self):
        with pytest.raises(RuntimeError, match="cv.toml is not valid TOML"):
            parse_cv("format_version = ", source="cv.toml")


# -- rendering ----------------------------------------------------------------


class TestRendering:
    def test_every_declared_fact_reaches_the_page(self):
        cv = parse_cv(DOCUMENT)
        page = render_cv_markdown(cv)

        assert "# Ada Lovelace" in page
        assert "![Profile picture](pic.jpg)" in page
        assert "Analyst" in page
        assert "London, England" in page
        assert "[ada@example.org](mailto:ada@example.org)" in page
        assert "[example.org/ada](https://example.org/ada)" in page
        assert "I write [notes](https://example.org/notes) about engines." in page

        assert "- **Languages:** Analytical Engine notation, French" in page
        assert "- **Other:** Correspondence" in page

        assert "### Note G" in page
        assert "- The first published algorithm" in page
        assert "- **Technologies used:** Analytical Engine" in page
        assert "### Translation" in page

        assert "### Poetical science" in page
        assert "Imagination is the *discovering* faculty." in page

        assert "### Private tuition in mathematics" in page
        assert "- **Year:** 1833 - 1840" in page
        assert "- **Institute:** [University of London](https://london.example)" in page
        assert "- **Focus:** Mathematics" in page
        assert "- **Thesis:** On the Analytical Engine" in page
        assert "- [Course details](https://london.example/course)" in page

        assert "### Translator and analyst" in page
        assert "- **Period:** 1842 - 1843" in page
        assert "- **Company:** [Scientific Memoirs](https://memoirs.example)" in page
        assert "Translated Menabrea's memoir" in page
        assert "### Correspondent" in page
        assert "- **Company:** Self-employed" in page

        assert "- English – Native" in page
        assert "- [French](https://example.org/french) – Fluent" in page

        assert "Write to [ada@example.org](mailto:ada@example.org)." in page
        assert "Last updated on October 10th, 1852" in page

    def test_the_section_headings_are_the_documents_structure(self):
        page = render_cv_markdown(parse_cv(DOCUMENT))
        for heading in ("## Skills", "## Projects", "## Hobbies & interests",
                        "## Education", "## Work experience", "## Languages",
                        "## Contact information"):
            assert heading in page

    def test_an_absent_photo_emits_no_image(self):
        cv = parse_cv(DOCUMENT.replace('photo = "pic.jpg"\n', ""))
        assert "![Profile picture]" not in render_cv_markdown(cv)


# -- the Person a CV states ----------------------------------------------------


class TestPerson:
    def test_the_identity_comes_from_the_declared_author(self):
        person = cv_person_jsonld(parse_cv(DOCUMENT), TEST_AUTHOR)
        assert person["@type"] == "Person"
        assert person["name"] == TEST_AUTHOR["name"]
        assert person["url"] == TEST_AUTHOR["url"]

    def test_a_fuller_spelling_of_the_name_rides_as_an_alternate(self):
        person = cv_person_jsonld(parse_cv(DOCUMENT), TEST_AUTHOR)
        assert person["alternateName"] == "Ada Lovelace"

    def test_the_same_name_is_not_repeated_as_an_alternate(self):
        author = {**TEST_AUTHOR, "name": "Ada Lovelace"}
        person = cv_person_jsonld(parse_cv(DOCUMENT), author)
        assert "alternateName" not in person

    def test_the_cv_contributes_what_a_cv_knows(self):
        person = cv_person_jsonld(parse_cv(DOCUMENT), TEST_AUTHOR)
        assert person["jobTitle"] == "Analyst"
        assert person["email"] == "mailto:ada@example.org"
        assert person["address"]["addressLocality"] == "London, England"
        assert [lang["name"] for lang in person["knowsLanguage"]] == [
            "English", "French",
        ]
        assert person["alumniOf"] == [{
            "@type": "EducationalOrganization",
            "name": "University of London",
            "url": "https://london.example",
        }]

    def test_declared_profiles_join_same_as_without_repeating(self):
        author = {
            **TEST_AUTHOR,
            "same_as": ["https://example.org/ada", "https://elsewhere.example"],
        }
        person = cv_person_jsonld(parse_cv(DOCUMENT), author)
        assert person["sameAs"] == [
            "https://example.org/ada", "https://elsewhere.example",
        ]

    def test_a_profile_the_author_never_declared_is_added(self):
        person = cv_person_jsonld(parse_cv(DOCUMENT), TEST_AUTHOR)
        assert person["sameAs"] == [
            *TEST_AUTHOR["same_as"], "https://example.org/ada",
        ]

    def test_a_build_with_no_author_refuses(self):
        with pytest.raises(ValueError, match="author"):
            cv_person_jsonld(parse_cv(DOCUMENT), None)


# -- the directive -------------------------------------------------------------


class TestDirective:
    def _project(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir(exist_ok=True)
        (docs / "cv.toml").write_text(DOCUMENT, encoding="utf-8")
        return tmp_path

    def test_the_directive_renders_the_document(self, tmp_path):
        project = self._project(tmp_path)
        result = resolve_content(
            "cv", {"path": "docs/cv.toml"}, [], str(project),
            config={"author": dict(TEST_AUTHOR)},
        )
        assert "# Ada Lovelace" in result
        assert CV_PERSON_ATTR in result

    def test_the_person_survives_the_markdown_conversion(self, tmp_path):
        """The payload crosses the converter, links in the prose and all."""
        from selfdoc_core.html import md_to_html

        project = self._project(tmp_path)
        result = resolve_content(
            "cv", {"path": "docs/cv.toml"}, [], str(project),
            config={"author": dict(TEST_AUTHOR)},
        )
        person = json.loads(extract_cv_person(md_to_html(result)))
        assert person["@type"] == "Person"
        assert person["jobTitle"] == "Analyst"
        assert "<a href=" not in person["description"]

    def test_a_payload_that_is_not_json_is_refused(self):
        with pytest.raises(RuntimeError, match="does not decode"):
            extract_cv_person(f'<div {CV_PERSON_ATTR}="bm90IGpzb24="></div>')

    def test_a_page_with_no_cv_carries_no_person(self):
        assert extract_cv_person("<p>An ordinary page.</p>") is None

    def test_a_missing_path_is_refused(self, tmp_path):
        with pytest.raises(RuntimeError, match="path="):
            resolve_content("cv", {}, [], str(tmp_path), config={})

    def test_a_document_that_is_not_there_is_refused(self, tmp_path):
        with pytest.raises(RuntimeError, match="not a file"):
            resolve_content(
                "cv", {"path": "docs/cv.toml"}, [], str(tmp_path), config={},
            )

    def test_a_build_with_no_author_refuses(self, tmp_path):
        project = self._project(tmp_path)
        with pytest.raises(ValueError, match="author"):
            resolve_content(
                "cv", {"path": "docs/cv.toml"}, [], str(project), config={},
            )


# -- the page the build writes -------------------------------------------------


class TestCvPageBuild:
    def _build(self, tmp_path):
        from selfdoc.build import build

        project = tmp_path / "site"
        docs = project / "docs"
        docs.mkdir(parents=True)
        (project / "src").mkdir()
        (project / "src" / "__init__.py").write_text('"""x."""\n')
        (docs / "cv.toml").write_text(DOCUMENT, encoding="utf-8")
        (docs / "index.md").write_text("# Home\n\nWelcome.\n", encoding="utf-8")
        (docs / "cv.md").write_text(
            "---\n"
            "title: CV\n"
            f"type: {CV_PAGE_TYPE}\n"
            "description: The curriculum vitae of Ada Lovelace, analyst.\n"
            "---\n"
            "\n"
            ':-: cv path="docs/cv.toml"\n',
            encoding="utf-8",
        )
        (project / "selfdoc.json").write_text(
            json.dumps(default_config()), encoding="utf-8",
        )
        build(str(project))
        with open(
            os.path.join(str(project), "docs", "_build", "cv", "index.html"),
            "r", encoding="utf-8",
        ) as f:
            return f.read()

    def _ld(self, page):
        return [
            json.loads(block)
            for block in re.findall(
                r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
                page, re.DOTALL,
            )
        ]

    def test_the_page_is_a_profile_page(self, tmp_path):
        objects = self._ld(self._build(tmp_path))
        assert any(obj.get("@type") == "ProfilePage" for obj in objects)

    def test_the_page_carries_the_person(self, tmp_path):
        objects = self._ld(self._build(tmp_path))
        person = next(o for o in objects if o.get("@type") == "Person")
        assert person["jobTitle"] == "Analyst"
        assert person["alternateName"] == "Ada Lovelace"
        assert [lang["name"] for lang in person["knowsLanguage"]] == [
            "English", "French",
        ]

    def test_the_page_carries_every_section(self, tmp_path):
        page = self._build(tmp_path)
        for heading in ("Skills", "Projects", "Hobbies &amp; interests",
                        "Education", "Work experience", "Languages",
                        "Contact information"):
            assert heading in page

    def test_the_page_carries_every_entry(self, tmp_path):
        page = self._build(tmp_path)
        for entry in ("Analytical Engine notation", "Correspondence", "Note G",
                      "The first published algorithm", "Translation",
                      "Poetical science", "Private tuition in mathematics",
                      "On the Analytical Engine", "Translator and analyst",
                      "Correspondent", "Self-employed", "Native", "Fluent",
                      "October 10th, 1852"):
            assert entry in page, entry
