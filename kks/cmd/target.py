    targets = resource_stream('kks', f'data/{target_file}')
    workspace_targets = path / target_file

    if workspace_targets.exists():
        if workspace_targets.is_file():
            click.secho(f'The file {target_file} already exists', fg='yellow')
        else:
            click.secho(f'"{target_file}" exists and is not a file, you will need to replace it to create custom targets', fg='red')
        workspace_targets = workspace_targets.with_suffix(workspace_targets.suffix + '.default')
        click.secho(f'Saving default targets to "{workspace_targets.name}"\n', fg='green')
    workspace_targets.write_bytes(targets.read())

