package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.TasSave;
import io.github.asgerjon.unittas.TasSuite;
import io.github.asgerjon.unittas.TasTestCase;
import net.minecraft.block.Block;
import net.minecraft.server.MinecraftServer;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Collections;
import java.util.List;

/**
 * Save mode's own check (SPEC.md 9.3 step 9), on the self-check saves the probe's test_oldsaves makes
 * (run/oldsaves/selfcheck: test worlds with a gold marker block, and a building list naming it). Each save is opened as
 * found and again as this game saved it, by `./unittas.sh oldsaves dev@selfcheck` or `unittas run --java oldsaves`.
 * Its Python twin, by the same names, is python/tests/selfsuite/oldsaves.py. Outside save mode it skips itself, and so
 * does testB on a save with no marker (a vanilla one).
 */
@TasSuite("oldsaves")
public class SaveTests extends TasTestCase {

	@Override
	protected void setUp() {
		if (TasSave.current() == null) {
			skipTest("not in save mode");
		}
	}

	public void testA_loadedWithoutErrors() {
		assertEqual(Collections.emptyList(), TasSave.current().loadErrors, "logged while the save loaded");
	}

	public void testB_itsMarkerIsThere() {
		int[] at = marker(TasSave.current());
		if (at == null) {
			skipTest("no marker in its building list: not a self-check save");
		}
		Block found = onServer(() -> world().getBlock(at[0], at[1], at[2]));
		assertEqual("minecraft:gold_block", Block.blockRegistry.getNameForObject(found), "the marker at " + at[0] + " "
			+ at[1] + " " + at[2]);
	}

	public void testC_theOneNamedIsOpen() {
		assertEqual(TasSave.current().folder, onServer(() -> MinecraftServer.getServer().getFolderName()));
	}

	/**
	 * The marker's block from the save's building list (`name dim x1 y1 z1 x2 y2 z2 view ...`, as
	 * oldsaves/make_vanilla_worlds.py writes it): the corner of the building named marker, or null without one.
	 */
	static int[] marker(TasSave save) {
		if (save.buildings == null || !save.buildings.isFile()) {
			return null;
		}
		List<String> lines;
		try {
			lines = Files.readAllLines(save.buildings.toPath(), StandardCharsets.UTF_8);
		} catch (IOException e) {
			throw new AssertionError("can't read " + save.buildings + ": " + e);
		}
		for (String line : lines) {
			String[] words = line.trim().split("\\s+");
			if (words.length >= 5 && "marker".equals(words[0])) {
				return new int[]{Integer.parseInt(words[2]), Integer.parseInt(words[3]), Integer.parseInt(words[4])};
			}
		}
		return null;
	}
}
