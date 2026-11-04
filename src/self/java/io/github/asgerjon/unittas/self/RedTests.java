package io.github.asgerjon.unittas.self;

import io.github.asgerjon.unittas.ExpectedFailure;
import io.github.asgerjon.unittas.TasSuite;
import io.github.asgerjon.unittas.TasTestCase;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.StandardOpenOption;

/**
 * The self-red suite: tests whose report is meant to be red, in known ways, for what a green run can't show (the
 * report's outcomes and counts, the warnings, what the run puts back after it). Never all ok: run it as
 * `./unittas.sh "self,self-red,nosuch"` and check the report with `python3 bin/self_red_check.py`, which knows what
 * every line should say.
 */
@TasSuite("self-red")
public class RedTests extends TasTestCase {

	/** Appended to forge.cfg by a test, and gone again once the run has put the config back. */
	public static final String CONFIG_MARK = "# changed by unitTAS's self-red run";
	public static final String CONFIG_MADE = "unittas-red.cfg";

	@ExpectedFailure("a failed assert is the expected failure")
	public void testExpectedAssertion() {
		assertEqual(1, 2);
	}

	@ExpectedFailure("an exception from the test itself is one too")
	public void testExpectedException() {
		throw new IllegalStateException("thrown on purpose");
	}

	@ExpectedFailure("this mark has done its work: the test passes")
	public void testUnexpectedSuccess() {
		assertEqual(1, 1);
	}

	public void testWarnsOutsideAStep() {
		// the server's player, read from the test thread rather than in onServer: a warning, not a failure (yet)
		assertIsNotNone(player());
	}

	public void testLeavesTheConfigChanged() throws IOException {
		File config = new File(mc().mcDataDir, "config");
		Files.write(new File(config, "forge.cfg").toPath(), ("\n" + CONFIG_MARK + "\n").getBytes(StandardCharsets.UTF_8),
			StandardOpenOption.APPEND);
		Files.write(new File(config, CONFIG_MADE).toPath(), "made by unitTAS's self-red run\n".getBytes(StandardCharsets.UTF_8));
	}
}
