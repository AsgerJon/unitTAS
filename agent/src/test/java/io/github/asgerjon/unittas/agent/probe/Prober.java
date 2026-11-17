package io.github.asgerjon.unittas.agent.probe;

import io.github.asgerjon.unittas.agent.game.Entity;
import io.github.asgerjon.unittas.agent.game.Named;
import io.github.asgerjon.unittas.agent.game.Player;
import io.github.asgerjon.unittas.agent.game.World;

import java.util.ArrayList;
import java.util.List;

/**
 * RenameCheck's probe (SPEC.md 19.7 step 6b), written and compiled in the game's Mojang names: every kind of
 * reference a port makes, renamed as it loads. run() says what it saw, the same before renaming and after.
 */
public final class Prober {

	private Prober() {
	}

	public static String run() {
		World world = new World();
		List<String> heard = new ArrayList<>();
		// a lambda for the game's own interface
		world.listen(entity -> heard.add(entity.describe()));
		Player player = new Player();
		world.add(player);
		// a method declared up the hierarchy, overridden in between
		player.tick();
		Entity[] many = Entity.many(2);
		Ticker ticker = new Ticker();
		ticker.tick();
		world.add(ticker);
		// generics, and a game class as a constant
		Player found = world.first(Player.class);
		List<Entity> all = world.entities();
		// a nested class of the game's by its source name, as javac finds it in the stubs
		Player.Hand hand = player.hand;
		return String.join(",", heard) + ";" + player.getX() + ";" + found.name() + ";" + player.greeting() + ";"
			+ hand + ";" + many.length + ";" + ticker.x + ";" + Entity.made + ";" + (found instanceof Named)
			+ ";" + all.size();
	}
}
