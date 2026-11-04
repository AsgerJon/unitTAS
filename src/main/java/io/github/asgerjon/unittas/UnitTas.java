package io.github.asgerjon.unittas;

import cpw.mods.fml.common.FMLCommonHandler;
import cpw.mods.fml.common.discovery.ASMDataTable;
import net.minecraft.client.Minecraft;
import net.minecraftforge.common.MinecraftForge;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Properties;

/**
 * unitTAS: tests that play the real game, in the manner of Python's unittest (see README.md). Asleep unless
 * ./unittas.sh left a request in the client's folder (`unittas/request.properties`). Then it makes a fresh test world
 * from the main menu, runs the asked-for suites on their own thread, writes the report and screenshots to the results
 * folder and quits the game. The request is used up at once, so a crash never leaves the next ordinary run in test
 * mode.
 */
public final class UnitTas {

	static final Logger LOG = LogManager.getLogger("unitTAS");

	/** What ./unittas.sh asked for. */
	static final class Request {
		final List<String> suites;
		/** Only tests whose `Class.method` name contains this, or null for all. */
		final String filter;
		final File results;
		/**
		 * Saves to open instead of the fresh test world: their folder names in the game's saves, each opened in turn
		 * (twice: as found, then as this game saved it), the suites run in each with no resets between tests.
		 */
		final List<String> saves;
		/** Where the pristine copies of those saves and their building lists are. */
		final File oldSaves;
		/** Someone watches the run (most likely an LLM): alarms instead of fixed limits (TasWatch). */
		final boolean watched;
		/** Seconds between the watch's live pictures; 0 for none. */
		final int watchPictures;
		/** Seconds an alarm waits for its answer before unitTAS does what it does unwatched. */
		final int watchDecide;

		Request(Properties properties) {
			String suiteList = properties.getProperty("suites", "").trim();
			suites = suiteList.isEmpty() ? new ArrayList<>(TasSuites.names()) : Arrays.asList(suiteList.split("[,\\s]+"));
			String only = properties.getProperty("filter", "").trim();
			filter = only.isEmpty() ? null : only;
			results = new File(properties.getProperty("results", "unittas-results"));
			String saveList = properties.getProperty("saves", "").trim();
			saves = saveList.isEmpty() ? new ArrayList<>() : Arrays.asList(saveList.split("[,\\s]+"));
			String pristine = properties.getProperty("oldsaves", "").trim();
			oldSaves = pristine.isEmpty() ? null : new File(pristine);
			watched = Boolean.parseBoolean(properties.getProperty("watched", "false").trim());
			watchPictures = Math.max(0, number(properties, "watch.pictures", 10));
			watchDecide = Math.max(10, number(properties, "watch.decide", 300));
		}

		private static int number(Properties properties, String key, int otherwise) {
			try {
				return Integer.parseInt(properties.getProperty(key, "").trim());
			} catch (NumberFormatException e) {
				return otherwise;
			}
		}

		/** One line for the script to show, also logged. */
		void progress(String line) {
			LOG.info(line);
			if (!results.isDirectory() && !results.mkdirs()) {
				return;
			}
			try (Writer out = new OutputStreamWriter(new FileOutputStream(new File(results, "progress.txt"), true), StandardCharsets.UTF_8)) {
				out.write(line + "\n");
			} catch (IOException e) {
				LOG.warn("Can't write progress", e);
			}
		}
	}

	private UnitTas() {
	}

	/** From UnitTasMod's preInit, on the client: a run, if ./unittas.sh asked for one; otherwise nothing at all. */
	static void preInit(ASMDataTable table) {
		File request = UnitTasMode.request(Minecraft.getMinecraft().mcDataDir);
		if (!request.isFile()) {
			return;
		}
		TasSuites.find(table);
		TasPlugins.find(table);
		start(request);
	}

	private static void start(File requestFile) {
		Properties properties = new Properties();
		try (InputStream in = new FileInputStream(requestFile)) {
			properties.load(in);
		} catch (IOException e) {
			LOG.error("Can't read {}", requestFile, e);
			return;
		} finally {
			if (!requestFile.delete()) {
				LOG.warn("Can't remove {}; delete it before the next ordinary run", requestFile);
			}
		}
		UnitTasMode.running = true;
		Request request = new Request(properties);
		request.progress("unitTAS started: suites " + String.join(", ", request.suites)
			+ (request.filter == null ? "" : ", only tests matching '" + request.filter + "'")
			+ (request.saves.isEmpty() ? "" : ", in the saves " + String.join(", ", request.saves))
			+ (request.watched ? "; watched: alarms in " + new File(request.results, "alarm.txt").getAbsolutePath() : ""));
		for (String problem : TasPlugins.problems()) {
			request.progress(problem);
		}
		TasGame game = new TasGame(request);
		FMLCommonHandler.instance().bus().register(game);
		MinecraftForge.EVENT_BUS.register(game);
		game.startWatch();
	}
}
