"""Repository layout discovery and non-destructive grouped initialization."""

import json

import yaml

from ubiq.cli import main


def write(root, name, body=''):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def test_discover_groups_assets_and_distinguishes_context_evidence(tmp_path, capsys):
    sources = {
        'skills/review/SKILL.md': '---\nname: review\n---\nReview changes.',
        '.cursor/rules/style.mdc': '---\ndescription: Style\n---\nUse plain names.',
        'packages/billing/scripts/check.py': 'print("ok")',
        'scripts/hooks/post-commit': '#!/bin/sh\ntrue',
        'src/ordering/GLOSSARY.md': '# Ordering\n',
        'src/billing/invoice.py': '',
        'src/shared/types.py': '',
        'node_modules/pkg/scripts/no.sh': '',
        '.git/hooks/no': '',
        'dist/scripts/no.sh': '',
    }
    for name, body in sources.items():
        write(tmp_path, name, body)
    external = tmp_path.parent / (tmp_path.name + '-external')
    write(external, 'scripts/no.sh')
    (tmp_path / 'external').symlink_to(external, target_is_directory=True)
    assert main(['discover', '--root', str(tmp_path), '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['groups']['skills/review']['skills'] == ['skills/review/SKILL.md']
    assert result['groups']['packages/billing/scripts']['scripts'] == ['packages/billing/scripts/check.py']
    assert result['groups']['scripts/hooks']['hooks'] == ['scripts/hooks/post-commit']
    assert result['groups']['.cursor/rules']['rules'] == ['.cursor/rules/style.mdc']
    assert {c['path']: c['evidence'] for c in result['contexts']} == {
        'packages/billing': 'directory', 'src/billing': 'directory',
        'src/ordering': 'glossary',
    }
    assert not (tmp_path / '.ubiq').exists()
    assert all('no' not in p for group in result['groups'].values() for paths in group.values() for p in paths)


def test_init_registers_all_asset_families_without_editing_sources(tmp_path, capsys):
    sources = {
        'skills/review/SKILL.md': '---\nname: review\n---\nReview changes.',
        'cursor/rules/style.mdc': '---\ntitle: Style\n---\nUse plain names.',
        'scripts/check.sh': '#!/bin/sh\ntrue',
        'packages/billing/scripts/check.sh': '#!/bin/sh\ntrue',
        '.githooks/post-commit': '#!/bin/sh\ntrue',
    }
    for name, body in sources.items():
        write(tmp_path, name, body)
    assert main(['init', '--root', str(tmp_path)]) == 0
    catalog = json.loads((tmp_path / '.ubiq/catalogs/assets.json').read_text())
    assert set(catalog) == {'skills', 'rules', 'scripts', 'hooks'}
    assert len(catalog['scripts']) == 2
    assert catalog['skills'] == ['skill:review']
    assert catalog['rules'] == ['rule:style']
    assert main(['check', '--root', str(tmp_path), '--json']) == 0
    capsys.readouterr()
    for name, body in sources.items():
        assert (tmp_path / name).read_text() == body
    catalog['hooks'].clear()
    (tmp_path / '.ubiq/catalogs/assets.json').write_text(json.dumps(catalog))
    assert main(['check', '--root', str(tmp_path), '--json']) == 1
    assert any(d['code'] == 'E007' for d in json.loads(capsys.readouterr().out)['diagnostics'])


def test_init_preserves_existing_metadata_and_refuses_collisions(tmp_path, capsys):
    write(tmp_path, 'scripts/check.sh', 'true')
    prior = write(tmp_path, '.ubiq/catalogs/assets.json', '{"keep": true}')
    assert main(['init', '--root', str(tmp_path)]) == 1
    assert prior.read_text() == '{"keep": true}'
    assert not (tmp_path / 'ubiq.yaml').exists()


def test_discover_respects_config_ignore_and_does_not_invent_contexts(tmp_path, capsys):
    write(tmp_path, 'ubiq.yaml', 'ignore: [private/**]\n')
    write(tmp_path, 'private/scripts/secret.py')
    write(tmp_path, 'scripts/setup.sh')
    write(tmp_path, 'src/utils/helper.py')
    assert main(['discover', '--root', str(tmp_path), '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert list(result['groups']) == ['scripts']
    assert result['contexts'] == []


def test_init_includes_existing_domain_glossaries_as_scan_roots(tmp_path, capsys):
    write(tmp_path, 'services/billing/GLOSSARY.md', '# Billing\n')
    write(tmp_path, 'GLOSSARY-MAP.md', '# Contexts\n')
    assert main(['init', '--root', str(tmp_path)]) == 0
    config = yaml.safe_load((tmp_path / 'ubiq.yaml').read_text())
    assert 'services/billing/GLOSSARY.md' in config['docs']
    assert 'GLOSSARY-MAP.md' in config['docs']
    report = json.loads((tmp_path / '.ubiq/discovery.json').read_text())
    assert report['contexts'] == [{'path': 'services/billing', 'evidence': 'glossary'}]


def test_schema_proposals_follow_file_metadata_and_keep_mixed_formats_separate(tmp_path, capsys):
    write(tmp_path, 'src/billing/glossary/invoice.md',
          '---\nterm: Invoice\nns: billing\naliases: [Bill]\nid: BILL-1\n---\nA payment request.')
    write(tmp_path, 'src/billing/glossary/payment.md',
          '---\ntitle: Payment\n---\nMoney received.')
    write(tmp_path, 'src/billing/glossary/account.md',
          '---\nentity: Account\n---\nA customer account.')
    write(tmp_path, 'skills/review/SKILL.md', '---\nname: review\n---\nReview changes.')
    write(tmp_path, 'scripts/setup.sh', '#!/bin/sh\ntrue')
    assert main(['discover', '--root', str(tmp_path), '--json']) == 0
    report = json.loads(capsys.readouterr().out)
    by_file = {source: schema for schema in report['schemas'] for source in schema['files']}
    invoice = by_file['src/billing/glossary/invoice.md']
    assert invoice['term_field'] == 'term'
    assert invoice['ns'] == 'billing' and invoice['namespace_evidence'] == 'frontmatter'
    assert invoice['fields'] == ['aliases', 'id', 'ns', 'term']
    payment = by_file['src/billing/glossary/payment.md']
    assert payment['term_field'] == 'title'
    assert payment['ns'] == 'billing' and payment['namespace_evidence'] == 'directory-candidate'
    assert by_file['src/billing/glossary/account.md']['term_field'] is None
    assert by_file['skills/review/SKILL.md']['term_field'] == 'name'
    assert by_file['scripts/setup.sh']['storage'] == 'overlay'
    assert by_file['scripts/setup.sh']['name_source'] == 'relative_path'
    assert not (tmp_path / 'ubiq.yaml').exists()


def test_init_preserves_overlay_metadata_without_a_source_naming_field(tmp_path, capsys):
    write(tmp_path, 'rules/policy.mdc',
          '---\nns: billing\naliases: [invoice-policy]\nid: POLICY-1\ndescription: Policy\n---\nRule body.')
    write(tmp_path, 'README.md', '[[billing:invoice-policy]] and [[POLICY-1]].')
    assert main(['init', '--root', str(tmp_path)]) == 0
    capsys.readouterr()
    catalog = json.loads((tmp_path / '.ubiq/catalogs/assets.json').read_text())
    assert catalog['rules'] == ['billing:rules/policy.mdc']
    assert main(['check', '--root', str(tmp_path), '--json']) == 0
    assert json.loads(capsys.readouterr().out)['errors'] == 0


def test_init_keeps_existing_grouped_glossary_out_of_asset_classification(tmp_path, capsys):
    write(tmp_path, '.ubiq/glossary/rules/style.md', '---\nterm: style\nns: rule\n---\nNaming style.')
    assert main(['init', '--root', str(tmp_path)]) == 0
    capsys.readouterr()
    assert main(['check', '--root', str(tmp_path), '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['errors'] == 0 and result['terms'] == 2
    report = json.loads((tmp_path / '.ubiq/discovery.json').read_text())
    assert report['groups'] == {}
    assert report['schemas'][0]['ns'] == 'rule'


def test_init_escapes_literal_paths_in_glossary_and_coverage_globs(tmp_path, capsys):
    write(tmp_path, 'skills/review[1]/SKILL.md', '---\nname: review\n---\nReview changes.')
    write(tmp_path, 'scripts/check[1].sh', 'true')
    write(tmp_path, 'services/billing[1]/GLOSSARY.md', '# Billing\n')
    assert main(['init', '--root', str(tmp_path)]) == 0
    capsys.readouterr()
    assert main(['check', '--root', str(tmp_path), '--json']) == 0
    capsys.readouterr()
    config = yaml.safe_load((tmp_path / 'ubiq.yaml').read_text())
    assert 'services/billing[[]1]/GLOSSARY.md' in config['docs']
    path = tmp_path / '.ubiq/catalogs/assets.json'
    catalog = json.loads(path.read_text())
    catalog['scripts'].clear()
    path.write_text(json.dumps(catalog))
    assert main(['check', '--root', str(tmp_path), '--json']) == 1
    assert any(d['code'] == 'E007' for d in json.loads(capsys.readouterr().out)['diagnostics'])
